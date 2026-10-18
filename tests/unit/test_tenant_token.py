"""
Unit tests for cryptographic tenant tokens and tenant identity resolution.
Verifies HMAC-SHA256 signature verification, tampering defense, expiration, and header resolution.
"""

import time
import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests.auth_helpers import ENROLLMENT_KEY
from services.security.tenant_token import (
    TenantIssuanceDeniedError,
    TenantIssuanceUnavailableError,
    TenantTokenError,
    TenantTokenExpiredError,
    TenantTokenInvalidError,
    authorize_token_issuance,
    issue_tenant_token,
    resolve_tenant_identity,
    verify_tenant_token,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_issue_and_verify_valid_token():
    token = issue_tenant_token("SME-ALPHA-01", ttl_seconds=3600)
    assert "." in token
    verified_tenant = verify_tenant_token(token)
    assert verified_tenant == "SME-ALPHA-01"


def test_tampered_token_signature_rejected():
    token = issue_tenant_token("SME-ALPHA-01", ttl_seconds=3600)
    payload, sig = token.split(".")
    tampered = f"{payload}.{sig[:-4]}XXXX"
    with pytest.raises(TenantTokenInvalidError, match="Invalid tenant token signature"):
        verify_tenant_token(tampered)


def test_expired_token_rejected():
    token = issue_tenant_token("SME-EXPIRED", ttl_seconds=-10)
    with pytest.raises(TenantTokenExpiredError, match="expired"):
        verify_tenant_token(token)


def test_resolve_tenant_identity_precedence():
    valid_token = issue_tenant_token("TOKEN-TENANT", ttl_seconds=3600)

    # 1. X-Tenant-Token takes highest precedence
    resolved = resolve_tenant_identity(
        x_tenant_token=valid_token,
        authorization="Bearer some_other",
        x_tenant_id="LEGACY-TENANT",
    )
    assert resolved == "TOKEN-TENANT"

    # 2. Authorization: Bearer
    resolved_bearer = resolve_tenant_identity(
        x_tenant_token=None,
        authorization=f"Bearer {valid_token}",
        x_tenant_id="LEGACY-TENANT",
    )
    assert resolved_bearer == "TOKEN-TENANT"

    # 3. Fallback to client-asserted legacy X-Tenant-ID
    resolved_legacy = resolve_tenant_identity(
        x_tenant_token=None,
        authorization=None,
        x_tenant_id="LEGACY-TENANT",
    )
    assert resolved_legacy == "LEGACY-TENANT"

    # 4. Default fallback
    resolved_default = resolve_tenant_identity(
        x_tenant_token=None,
        authorization=None,
        x_tenant_id=None,
    )
    assert resolved_default == "SME-DEFAULT"


def test_per_tenant_map_rejects_tenants_missing_from_it(monkeypatch):
    monkeypatch.setenv("TENANT_ENROLLMENT_KEYS", '{"SME-ALPHA": "alpha-key"}')
    monkeypatch.setenv("TENANT_ENROLLMENT_KEY", "master-key")

    authorize_token_issuance("SME-ALPHA", "alpha-key")
    with pytest.raises(TenantIssuanceDeniedError):
        # The single key is not a wildcard once a per-tenant map exists.
        authorize_token_issuance("SME-BETA", "master-key")
    with pytest.raises(TenantIssuanceDeniedError):
        authorize_token_issuance("SME-ALPHA", "master-key")


def test_single_key_can_be_bound_to_one_tenant(monkeypatch):
    monkeypatch.delenv("TENANT_ENROLLMENT_KEYS", raising=False)
    monkeypatch.delenv("TENANT_ENROLLMENT_ALLOW_ANY_TENANT", raising=False)
    monkeypatch.setenv("TENANT_ENROLLMENT_KEY", "master-key")
    monkeypatch.setenv("TENANT_ENROLLMENT_TENANT_ID", "SME-ONLY")

    authorize_token_issuance("SME-ONLY", "master-key")
    with pytest.raises(TenantIssuanceDeniedError):
        authorize_token_issuance("SME-OTHER", "master-key")
    with pytest.raises(TenantIssuanceDeniedError):
        authorize_token_issuance("SME-ONLY", "wrong-key")


def test_unbound_single_key_is_closed_by_default(monkeypatch):
    monkeypatch.delenv("TENANT_ENROLLMENT_KEYS", raising=False)
    monkeypatch.delenv("TENANT_ENROLLMENT_TENANT_ID", raising=False)
    monkeypatch.delenv("TENANT_ENROLLMENT_ALLOW_ANY_TENANT", raising=False)
    monkeypatch.setenv("TENANT_ENROLLMENT_KEY", "master-key")

    with pytest.raises(TenantIssuanceUnavailableError):
        authorize_token_issuance("SME-ANY", "master-key")


def test_unbound_single_key_requires_an_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("TENANT_ENROLLMENT_KEYS", raising=False)
    monkeypatch.delenv("TENANT_ENROLLMENT_TENANT_ID", raising=False)
    monkeypatch.setenv("TENANT_ENROLLMENT_KEY", "master-key")
    monkeypatch.setenv("TENANT_ENROLLMENT_ALLOW_ANY_TENANT", "1")

    authorize_token_issuance("SME-ANY", "master-key")
    with pytest.raises(TenantIssuanceDeniedError):
        authorize_token_issuance("SME-ANY", "wrong-key")


def test_auth_token_api_endpoints(client):
    # Issue token (issuance requires the tenant enrollment key)
    issue_resp = client.post(
        "/api/v1/auth/token",
        json={"tenant_id": "SME-VERIFY-001"},
        headers={"X-Enrollment-Key": ENROLLMENT_KEY},
    )
    assert issue_resp.status_code == 200
    data = issue_resp.json()
    assert data["tenant_id"] == "SME-VERIFY-001"
    token = data["access_token"]
    assert len(token) > 20

    # Verify via Authorization: Bearer
    verify_resp = client.get("/api/v1/auth/verify", headers={"Authorization": f"Bearer {token}"})
    assert verify_resp.status_code == 200
    assert verify_resp.json() == {"valid": True, "tenant_id": "SME-VERIFY-001"}

    # Verify via X-Tenant-Token
    verify_resp2 = client.get("/api/v1/auth/verify", headers={"X-Tenant-Token": token})
    assert verify_resp2.status_code == 200
    assert verify_resp2.json()["tenant_id"] == "SME-VERIFY-001"

    # Forged token rejected
    bad_resp = client.get("/api/v1/auth/verify", headers={"Authorization": "Bearer invalid.token.payload"})
    assert bad_resp.status_code == 401

    # Missing token rejected
    no_token_resp = client.get("/api/v1/auth/verify")
    assert no_token_resp.status_code == 401

    # Client-asserted X-Tenant-ID without a token rejected
    spoofed_resp = client.get("/api/v1/auth/verify", headers={"X-Tenant-ID": "SME-VERIFY-001"})
    assert spoofed_resp.status_code == 401
