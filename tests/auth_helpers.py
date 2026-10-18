"""Helpers for minting signed tenant identities in tests."""

from __future__ import annotations

import os

ENROLLMENT_KEY = os.environ.get("TENANT_ENROLLMENT_KEY", "test-enrollment-key")


def tenant_headers(client, tenant_id: str) -> dict[str, str]:
    """Issues a signed tenant token and returns the headers that authenticate it."""
    response = client.post(
        "/api/v1/auth/token",
        json={"tenant_id": tenant_id},
        headers={"X-Enrollment-Key": ENROLLMENT_KEY},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
