"""
Autonomous Liquidity Sentinel Background Daemon.

Runs continuously in the background of FastAPI lifespan, evaluating active tenant
ledgers, cash runway, and recurring obligations against configured alert thresholds.
Enforces the Three-Tier Security Gate: automated staging in Tier 2; execution strictly refused.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from services.calculations.cash_analysis import calculate_cash_analysis
from services.calculations.predictive_cash import calculate_predictive_cash
from services.ingestion.csv_parser import parse_bank_csv
from services.security.staging_ledger import StagingRequest, staging_ledger

logger = logging.getLogger(__name__)


class SentinelDaemon:
    """Thread-safe background sentinel daemon managing autonomous continuous treasury audits."""

    _instance: Optional[SentinelDaemon] = None
    _lock = threading.Lock()

    def __init__(self, interval_seconds: int = 60) -> None:
        raw_interval = os.environ.get("SENTINEL_SWEEP_INTERVAL_SECONDS", str(interval_seconds))
        try:
            parsed_interval = int(raw_interval)
        except ValueError:
            parsed_interval = interval_seconds
        self._interval_seconds = max(5, parsed_interval)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._started_at: Optional[datetime] = None
        self._last_sweep_at: Optional[datetime] = None
        self._cycle_count = 0
        self._last_sweep_summary: Dict[str, Any] = {
            "status": "INITIALIZED",
            "cycle": 0,
            "tenants_audited": 0,
            "deficits_detected": 0,
            "actions_staged": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def get_instance(cls) -> SentinelDaemon:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._stop_event.clear()
            self._started_at = datetime.now(timezone.utc)
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="sentinel-daemon")
            self._thread.start()
            logger.info("Sentinel background daemon started (interval=%ds).", self._interval_seconds)

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        logger.info("Sentinel background daemon stopped.")

    def _run_loop(self) -> None:
        # Initial sweep on startup
        try:
            self.sweep()
        except Exception as exc:
            logger.error("Initial sentinel startup sweep failed: %s", exc)

        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self._interval_seconds):
                break
            try:
                self.sweep()
            except Exception as exc:
                logger.error("Sentinel periodic sweep error: %s", exc)

    def trigger_sweep(self) -> Dict[str, Any]:
        """Manually triggers an immediate audit cycle on-demand."""
        return self.sweep()

    def sweep(self) -> Dict[str, Any]:
        """Executes one audit cycle across all active sessions and ledgers."""
        with self._lock:
            self._cycle_count += 1
            now = datetime.now(timezone.utc)
            self._last_sweep_at = now
            current_cycle = self._cycle_count

        tenants_audited = 0
        deficits_detected = 0
        actions_staged = 0

        try:
            from services.agent.session_store import session_store

            sessions = session_store.list_sessions() if hasattr(session_store, "list_sessions") else []
            for record in sessions:
                csv_content = getattr(record, "csv_content", None)
                if not csv_content:
                    continue

                tenant_id = getattr(record, "tenant_id", "SME-DEFAULT")
                tenants_audited += 1

                try:
                    raw_bytes = csv_content.encode("utf-8")
                    parsed = parse_bank_csv(raw_bytes)
                    if not parsed.accepted_rows:
                        continue

                    facts = getattr(record, "financial_facts", {}) or {}
                    threshold_days = int(facts.get("alert_threshold_days", 30))

                    analysis = calculate_cash_analysis(
                        parsed.accepted_rows,
                        parsed.rejected_rows,
                        alert_threshold_days=threshold_days,
                    )

                    runway = analysis.runway_days
                    if runway is not None and runway <= threshold_days:
                        deficits_detected += 1
                        pred = calculate_predictive_cash(
                            current_balance=analysis.current_balance,
                            average_daily_burn=analysis.average_daily_burn,
                            rows=parsed.accepted_rows,
                            anchor_date=analysis.end_date,
                            projection_days=90,
                            target_horizon_days=threshold_days,
                            currency=analysis.currency,
                        )

                        if pred.has_projected_deficit and pred.recommended_bridge_amount > Decimal("0.00"):
                            # Check if a pending proposal is already staged for this tenant
                            existing = [
                                i for i in staging_ledger.list_intents(tenant_id=tenant_id)
                                if i.status == "STAGED_PENDING_HITL"
                            ]
                            if not existing:
                                bridge_cents = int(pred.recommended_bridge_amount * 100)
                                staging_ledger.stage_intent(
                                    StagingRequest(
                                        tenant_id=tenant_id,
                                        action_type="DRAW_CREDIT_LINE",
                                        amount_cents=bridge_cents,
                                        target_identifier=f"Harbor Community Bank (Sentinel: projected shortfall ${pred.projected_shortfall_amount} on {pred.projected_deficit_date})",
                                    )
                                )
                                actions_staged += 1
                                logger.info(
                                    "Sentinel auto-staged Tier 2 intent for tenant=%s: amount_cents=%d",
                                    tenant_id,
                                    bridge_cents,
                                )
                except Exception as exc:
                    logger.debug("Sentinel audit failed for session: %s", exc)

            summary = {
                "status": "HEALTHY",
                "cycle": current_cycle,
                "tenants_audited": tenants_audited,
                "deficits_detected": deficits_detected,
                "actions_staged": actions_staged,
                "timestamp": now.isoformat(),
            }
        except Exception as exc:
            summary = {
                "status": "ERROR",
                "error": str(exc),
                "cycle": current_cycle,
                "timestamp": now.isoformat(),
            }

        with self._lock:
            self._last_sweep_summary = summary
        return summary

    def get_telemetry(self) -> Dict[str, Any]:
        """Returns structured daemon telemetry for health probes and UI widgets."""
        with self._lock:
            return {
                "daemon_status": "RUNNING" if self._running else "STOPPED",
                "started_at": self._started_at.isoformat() if self._started_at else None,
                "last_sweep_at": self._last_sweep_at.isoformat() if self._last_sweep_at else None,
                "cycle_count": self._cycle_count,
                "interval_seconds": self._interval_seconds,
                "last_sweep_summary": self._last_sweep_summary,
            }


# Global singleton instance
sentinel_daemon = SentinelDaemon.get_instance()
