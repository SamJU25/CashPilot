"""FastAPI router for Autonomous Liquidity Sentinel Background Daemon.

Provides continuous background health probes and on-demand trigger endpoints
for the autonomous cash deficit detector and Tier 2 staging pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from services.sentinel.sentinel_daemon import sentinel_daemon

router = APIRouter(prefix="/api/v1/sentinel", tags=["Autonomous Sentinel"])


class SentinelTelemetryResponse(BaseModel):
    daemon_status: str
    started_at: Optional[str] = None
    last_sweep_at: Optional[str] = None
    cycle_count: int
    interval_seconds: int
    last_sweep_summary: Dict[str, Any]


class SentinelEvaluateResponse(BaseModel):
    status: str
    cycle: int
    tenants_audited: int = 0
    deficits_detected: int = 0
    actions_staged: int = 0
    timestamp: str
    error: Optional[str] = None


@router.get("/heartbeat", response_model=SentinelTelemetryResponse)
def get_sentinel_heartbeat() -> SentinelTelemetryResponse:
    """Returns continuous background telemetry for the Autonomous Liquidity Sentinel."""
    telemetry = sentinel_daemon.get_telemetry()
    return SentinelTelemetryResponse(**telemetry)


@router.post("/evaluate", response_model=SentinelEvaluateResponse)
def trigger_sentinel_evaluation() -> SentinelEvaluateResponse:
    """Triggers an on-demand audit cycle across active sessions and ledgers."""
    summary = sentinel_daemon.trigger_sweep()
    return SentinelEvaluateResponse(
        status=summary.get("status", "HEALTHY"),
        cycle=summary.get("cycle", 0),
        tenants_audited=summary.get("tenants_audited", 0),
        deficits_detected=summary.get("deficits_detected", 0),
        actions_staged=summary.get("actions_staged", 0),
        timestamp=summary.get("timestamp", ""),
        error=summary.get("error"),
    )
