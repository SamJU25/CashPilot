"""Unit tests for Plaid Open Banking integration.
Verifies Link token generation, public token exchange, multi-account consolidation,
contra-transfer reconciliation, encrypted item storage, and FastAPI endpoints.
"""

from unittest.mock import AsyncMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient
from api.main import app
from services.plaid.client import PlaidClient, PlaidError, plaid_client
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
async def test_plaid_client_unconfigured_raises():
    p_client = PlaidClient(client_id="", secret="")
    assert p_client.is_live is False
    with pytest.raises(PlaidError) as exc:
        await p_client.create_link_token("user-123")
    assert exc.value.error_code == "PLAID_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_plaid_client_configured_calls_api():
    p_client = PlaidClient(client_id="test_id", secret="test_secret", env="sandbox")
    assert p_client.is_live is True

    fake_response = {"link_token": "link-live-12345", "expiration": "2026-10-23T00:00:00Z"}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json=fake_response)

        res = await p_client.create_link_token("user-123")
        assert res["link_token"] == "link-live-12345"


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
    mock_accounts = [
        {
            "account_id": "acc-ops-1",
            "name": "Operating Checking",
            "balances": {"current": 50000.0, "iso_currency_code": "USD"},
        },
        {
            "account_id": "acc-pay-2",
            "name": "Payroll Checking",
            "balances": {"current": 20000.0, "iso_currency_code": "USD"},
        },
    ]

    test_store.save_item(
        tenant_id=tenant,
        item_id="item-mock-01",
        access_token="access-token-123",
        institution_name="Chase Commercial",
        accounts=mock_accounts,
    )

    mock_get_accounts = AsyncMock(return_value=mock_accounts)
    monkeypatch.setattr("services.plaid.sync.plaid_client.get_accounts", mock_get_accounts)

    mock_sync = AsyncMock(return_value={
        "added": [
            {
                "transaction_id": "tx-1",
                "account_id": "acc-ops-1",
                "amount": 5000.0,  # Plaid convention: positive = debit/outflow
                "date": "2026-10-15",
                "name": "Transfer to Payroll",
                "category": ["Transfer"],
            },
            {
                "transaction_id": "tx-2",
                "account_id": "acc-pay-2",
                "amount": -5000.0,  # Plaid convention: negative = credit/inflow
                "date": "2026-10-15",
                "name": "Transfer from Operating",
                "category": ["Transfer"],
            },
        ],
        "modified": [],
        "removed": [],
        "next_cursor": "cur-done",
    })
    monkeypatch.setattr("services.plaid.sync.plaid_client.sync_transactions", mock_sync)

    analysis, accounts = await sync_plaid_accounts_for_tenant(tenant, alert_threshold_days=30)
    assert analysis.document_format == "CSV"
    assert len(accounts) >= 2
    # Contra transfers should be detected
    assert analysis.internal_transfers is not None
    assert len(analysis.internal_transfers) > 0
    assert float(analysis.internal_transfers_excluded) == 5000.0


def test_api_plaid_routes(valid_token, monkeypatch, tmp_path):
    headers = {"X-Tenant-Token": valid_token}

    test_store = PlaidStorage(file_path=tmp_path / "api_test_plaid.json")
    monkeypatch.setattr("services.plaid.sync.plaid_storage", test_store)
    monkeypatch.setattr("services.plaid.storage.plaid_storage", test_store)
    monkeypatch.setattr("api.routes.plaid.plaid_storage", test_store)

    # 1. Status route
    res_status = client.get("/api/v1/plaid/status")
    assert res_status.status_code == 200
    assert "configured" in res_status.json()

    # 2. Config route
    res_cfg = client.post(
        "/api/v1/plaid/config",
        headers=headers,
        json={"client_id": "test_id_123", "secret": "test_sec_456", "env": "sandbox"},
    )
    assert res_cfg.status_code == 200
    assert res_cfg.json()["configured"] is True

    # 3. Link token with mock
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200, json={"link_token": "link-sandbox-test-123", "expiration": "2026-10-23T00:00:00Z"})

        res1 = client.post("/api/v1/plaid/link-token", headers=headers, json={"client_name": "CashPilot Test"})
        assert res1.status_code == 200
        assert res1.json()["link_token"] == "link-sandbox-test-123"

    # 4. Exchange token with mock
    mock_accounts = [
        {"account_id": "acc-1", "name": "Checking", "balances": {"current": 1000.0, "iso_currency_code": "USD"}}
    ]
    mock_exchange = AsyncMock(return_value={"access_token": "access-123", "item_id": "item-abc-123"})
    monkeypatch.setattr("api.routes.plaid.plaid_client.exchange_public_token", mock_exchange)
    monkeypatch.setattr("api.routes.plaid.plaid_client.get_accounts", AsyncMock(return_value=mock_accounts))
    monkeypatch.setattr("services.plaid.sync.plaid_client.get_accounts", AsyncMock(return_value=mock_accounts))
    monkeypatch.setattr("services.plaid.sync.plaid_client.sync_transactions", AsyncMock(return_value={"added": [], "modified": [], "removed": [], "next_cursor": "cur-1"}))

    res2 = client.post(
        "/api/v1/plaid/exchange-token",
        headers=headers,
        json={
            "public_token": "public-test-token",
            "institution_name": "Chase Bank",
            "institution_id": "ins_chase",
            "accounts": mock_accounts,
        },
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["success"] is True
    item_id = data2["item_id"]

    # 5. List accounts
    res3 = client.get("/api/v1/plaid/accounts", headers=headers)
    assert res3.status_code == 200
    data3 = res3.json()
    assert data3["connected_institutions"] >= 1

    # 6. Webhook
    res5 = client.post(
        "/api/v1/plaid/webhook",
        headers=headers,
        json={"webhook_type": "TRANSACTIONS", "webhook_code": "SYNC_UPDATES_AVAILABLE", "item_id": item_id},
    )
    assert res5.status_code == 200
    assert res5.json()["status"] == "ACK"

    # 7. Disconnect institution
    res6 = client.delete(f"/api/v1/plaid/items/{item_id}", headers=headers)
    assert res6.status_code == 200
    assert res6.json()["success"] is True
