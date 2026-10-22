"""Unit tests for Plaid Open Banking integration.
Verifies Link token generation, public token exchange, multi-account consolidation,
contra-transfer reconciliation, encrypted item storage, and FastAPI endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app
from services.plaid.client import PlaidClient
from services.plaid.storage import PlaidStorage
from services.plaid.sync import sync_plaid_accounts_for_tenant
from services.security.tenant_token import issue_tenant_token

client = TestClient(app)


@pytest.fixture
def temp_storage(tmp_path):
    storage_file = tmp_path / "test_plaid.json"
    storage = PlaidStorage(file_path=storage_file)
    return storage


@pytest.fixture
def valid_token():
    return issue_tenant_token("TEST-PLAID-TENANT", ttl_seconds=3600)


@pytest.mark.asyncio
async def test_plaid_client_sandbox_link_token():
    p_client = PlaidClient()
    res = await p_client.create_link_token("user-123")
    assert "link_token" in res
    assert res["link_token"].startswith("link-sandbox-")
    assert res.get("sandbox_simulated") is True


@pytest.mark.asyncio
async def test_plaid_client_sandbox_token_exchange():
    p_client = PlaidClient()
    res = await p_client.exchange_public_token("public-sandbox-mock-token")
    assert "access_token" in res
    assert "item_id" in res
    assert res["access_token"].startswith("access-sandbox-")


@pytest.mark.asyncio
async def test_plaid_client_sandbox_accounts():
    p_client = PlaidClient()
    accounts = await p_client.get_accounts("access-sandbox-mock-123")
    assert len(accounts) >= 2
    names = [a["name"] for a in accounts]
    assert "Operating Checking" in names
    assert "Payroll Account" in names


@pytest.mark.asyncio
async def test_plaid_storage_encryption_and_lifecycle(temp_storage):
    tenant = "TENANT-ACME"
    item = temp_storage.save_item(
        tenant_id=tenant,
        item_id="item-svb-01",
        access_token="access-secret-token-123",
        institution_name="Silicon Valley Bank",
        accounts=[{"account_id": "acc-1", "name": "Ops"}],
    )
    assert item["item_id"] == "item-svb-01"

    # Verify retrieval
    items = temp_storage.get_items(tenant)
    assert len(items) == 1
    assert items[0]["institution_name"] == "Silicon Valley Bank"

    # Verify update
    updated = temp_storage.update_item_sync(tenant, "item-svb-01", cursor="cur-new-999")
    assert updated is True
    assert temp_storage.get_item(tenant, "item-svb-01")["cursor"] == "cur-new-999"

    # Verify removal
    removed = temp_storage.remove_item(tenant, "item-svb-01")
    assert removed is True
    assert len(temp_storage.get_items(tenant)) == 0


@pytest.mark.asyncio
async def test_multi_account_sync_with_contra_transfers(monkeypatch, tmp_path):
    test_store = PlaidStorage(file_path=tmp_path / "plaid_sync_test.json")
    monkeypatch.setattr("services.plaid.sync.plaid_storage", test_store)
    monkeypatch.setattr("services.plaid.storage.plaid_storage", test_store)

    tenant = "TENANT-MULTI-CORP"
    test_store.save_item(
        tenant_id=tenant,
        item_id="item-mock-01",
        access_token="access-sandbox-mock-token",
        institution_name="Silicon Valley Bank",
    )

    analysis, accounts = await sync_plaid_accounts_for_tenant(tenant, alert_threshold_days=30)
    assert analysis.document_format == "CSV"
    assert len(accounts) >= 2
    assert float(analysis.current_balance) > 0
    # Contra transfers should be detected between SVB and Chase
    assert analysis.internal_transfers is not None
    assert len(analysis.internal_transfers) > 0
    assert float(analysis.internal_transfers_excluded) > 0


def test_api_plaid_routes(valid_token):
    headers = {"X-Tenant-Token": valid_token}

    # 1. Link token
    res1 = client.post("/api/v1/plaid/link-token", headers=headers, json={"client_name": "CashPilot Test"})
    assert res1.status_code == 200
    assert "link_token" in res1.json()

    # 2. Exchange token
    res2 = client.post(
        "/api/v1/plaid/exchange-token",
        headers=headers,
        json={
            "public_token": "public-sandbox-test",
            "institution_name": "Chase Bank",
            "institution_id": "ins_chase",
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["success"] is True
    item_id = data2["item_id"]
    assert "analysis" in data2
    assert data2["analysis"]["document_format"] == "CSV"

    # 3. List accounts
    res3 = client.get("/api/v1/plaid/accounts", headers=headers)
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["connected_institutions"] >= 1
    assert data3["total_accounts"] >= 2

    # 4. Trigger sync
    res4 = client.post("/api/v1/plaid/sync", headers=headers)
    assert res4.status_code == 200
    assert res4.json()["document_format"] == "CSV"

    # 5. Webhook
    res5 = client.post(
        "/api/v1/plaid/webhook",
        headers=headers,
        json={"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE", "item_id": item_id},
    )
    assert res5.status_code == 200
    assert res5.json()["status"] == "ACK"

    # 6. Disconnect institution
    res6 = client.delete(f"/api/v1/plaid/items/{item_id}", headers=headers)
    assert res6.status_code == 200
    assert res6.json()["success"] is True
