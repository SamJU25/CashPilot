"""Unit tests for SentinelDaemon and Sentinel API routes."""

from fastapi.testclient import TestClient

from api.main import app
from services.agent.session_store import session_store
from services.security.staging_ledger import staging_ledger
from services.sentinel.sentinel_daemon import SentinelDaemon, sentinel_daemon

client = TestClient(app)

DEFICIT_CSV = (
    "transaction_id,posted_on,amount,currency,description,closing_balance\n"
    "tx-1,2026-10-01,1000.00,USD,Inflow,10000.00\n"
    "tx-2,2026-10-05,-6000.00,USD,Heavy Outflow,4000.00\n"
    "tx-3,2026-10-10,-3500.00,USD,Payroll,500.00\n"
)


def test_sentinel_daemon_telemetry():
    telemetry = sentinel_daemon.get_telemetry()
    assert "daemon_status" in telemetry
    assert "cycle_count" in telemetry
    assert "interval_seconds" in telemetry
    assert "last_sweep_summary" in telemetry


def test_sentinel_daemon_sweep_empty():
    daemon = SentinelDaemon(interval_seconds=10)
    summary = daemon.sweep()
    assert summary["status"] == "HEALTHY"
    assert summary["cycle"] >= 1
    assert "timestamp" in summary


def test_sentinel_daemon_autonomous_detection_and_staging():
    staging_ledger.clear()
    tenant_id = "TENANT-SENTINEL-TEST"

    # Seed a session that triggers a projected cash deficit
    session_id = f"sentinel-test-session-{tenant_id}"
    session_store.update_statement(
        session_id=session_id,
        csv_content=DEFICIT_CSV,
        tenant_id=tenant_id,
    )
    session_store.set_financial_fact(session_id, "alert_threshold_days", 45)

    daemon = SentinelDaemon(interval_seconds=10)
    summary = daemon.sweep()

    assert summary["status"] == "HEALTHY"
    assert summary["tenants_audited"] >= 1
    assert summary["deficits_detected"] >= 1
    assert summary["actions_staged"] >= 1

    # Verify staged proposal in staging ledger (Tier 2, never auto-executed)
    intents = staging_ledger.list_intents(tenant_id=tenant_id)
    assert len(intents) == 1
    staged = intents[0]
    assert staged.action_type == "DRAW_CREDIT_LINE"
    assert staged.status == "STAGED_PENDING_HITL"
    assert staged.amount_cents > 0
    assert "Sentinel" in staged.target_identifier

    # Deduplication test: Running sweep again should NOT create duplicate staged intent
    summary_2 = daemon.sweep()
    assert summary_2["deficits_detected"] >= 1
    assert summary_2["actions_staged"] == 0
    intents_after = staging_ledger.list_intents(tenant_id=tenant_id)
    assert len(intents_after) == 1

    # Clean up
    staging_ledger.clear()
    session_store.clear(session_id)


def test_sentinel_heartbeat_api():
    resp = client.get("/api/v1/sentinel/heartbeat")
    assert resp.status_code == 200
    data = resp.json()
    assert "daemon_status" in data
    assert "cycle_count" in data
    assert "interval_seconds" in data
    assert "last_sweep_summary" in data


def test_sentinel_evaluate_api():
    resp = client.post("/api/v1/sentinel/evaluate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("HEALTHY", "ERROR")
    assert "cycle" in data
    assert "tenants_audited" in data
    assert "actions_staged" in data
    assert "timestamp" in data
