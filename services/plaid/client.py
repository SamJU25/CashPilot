"""Plaid API Client for Open Banking Integration.
Handles Link token creation, public token exchange, account metadata,
and read-only transaction synchronization via the official Plaid REST API.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PLAID_ENV_URLS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}


class PlaidError(Exception):
    """Raised when Plaid API returns an error or cannot be reached."""

    def __init__(self, message: str, error_code: str = "PLAID_ERROR", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


class PlaidClient:
    """Async client for Plaid Open Banking REST API.
    Operates strictly against the real Plaid API endpoints.
    """

    def __init__(
        self,
        client_id: str | None = None,
        secret: str | None = None,
        env: str | None = None,
    ):
        self.configure(client_id, secret, env)

    def configure(
        self,
        client_id: str | None = None,
        secret: str | None = None,
        env: str | None = None,
    ) -> None:
        """Update client credentials and environment."""
        self.client_id = (client_id or os.getenv("PLAID_CLIENT_ID") or "").strip()
        self.secret = (secret or os.getenv("PLAID_SECRET") or "").strip()
        self.env = (env or os.getenv("PLAID_ENV") or "sandbox").strip().lower()
        self.base_url = PLAID_ENV_URLS.get(self.env, "https://sandbox.plaid.com")
        self._is_live = bool(self.client_id and self.secret)

    @property
    def is_live(self) -> bool:
        """True if configured with Plaid API credentials."""
        return self._is_live

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "PLAID-CLIENT-ID": self.client_id,
            "PLAID-SECRET": self.secret,
        }

    def _ensure_configured(self) -> None:
        if not self._is_live:
            raise PlaidError(
                "Plaid credentials (PLAID_CLIENT_ID and PLAID_SECRET) are not configured. "
                "To connect live bank accounts, configure your Plaid keys.",
                error_code="PLAID_NOT_CONFIGURED",
                status_code=400,
            )

    async def create_link_token(
        self,
        client_user_id: str,
        client_name: str = "CashPilot",
        products: list[str] | None = None,
    ) -> dict[str, Any]:
        """Creates a Link token for the frontend Plaid Link modal."""
        self._ensure_configured()

        payload = {
            "client_id": self.client_id,
            "secret": self.secret,
            "client_name": client_name,
            "user": {"client_user_id": client_user_id},
            "products": products or ["transactions"],
            "country_codes": ["US"],
            "language": "en",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                res = await client.post(f"{self.base_url}/link/token/create", json=payload)
                data = res.json()
                if res.status_code != 200:
                    raise PlaidError(
                        data.get("error_message", "Failed to create Link token"),
                        error_code=data.get("error_code", "LINK_TOKEN_FAILED"),
                        status_code=res.status_code,
                    )
                return data
            except httpx.RequestError as exc:
                raise PlaidError(f"Plaid network error: {exc}", error_code="NETWORK_ERROR")

    async def exchange_public_token(self, public_token: str) -> dict[str, Any]:
        """Exchanges public_token from the Plaid Link modal for a permanent access_token."""
        self._ensure_configured()

        payload = {
            "client_id": self.client_id,
            "secret": self.secret,
            "public_token": public_token,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                res = await client.post(f"{self.base_url}/item/public_token/exchange", json=payload)
                data = res.json()
                if res.status_code != 200:
                    raise PlaidError(
                        data.get("error_message", "Failed to exchange public token"),
                        error_code=data.get("error_code", "TOKEN_EXCHANGE_FAILED"),
                        status_code=res.status_code,
                    )
                return data
            except httpx.RequestError as exc:
                raise PlaidError(f"Plaid network error: {exc}", error_code="NETWORK_ERROR")

    async def get_accounts(self, access_token: str) -> list[dict[str, Any]]:
        """Retrieves read-only account balance and metadata from Plaid."""
        self._ensure_configured()

        payload = {
            "client_id": self.client_id,
            "secret": self.secret,
            "access_token": access_token,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                res = await client.post(f"{self.base_url}/accounts/balance/get", json=payload)
                data = res.json()
                if res.status_code != 200:
                    raise PlaidError(
                        data.get("error_message", "Failed to get accounts"),
                        error_code=data.get("error_code", "ACCOUNTS_GET_FAILED"),
                        status_code=res.status_code,
                    )
                return data.get("accounts", [])
            except httpx.RequestError as exc:
                raise PlaidError(f"Plaid network error: {exc}", error_code="NETWORK_ERROR")

    async def sync_transactions(
        self,
        access_token: str,
        cursor: str | None = None,
        count: int = 100,
    ) -> dict[str, Any]:
        """Incremental transaction sync using Plaid /transactions/sync endpoint.
        Returns added, modified, removed transactions and next_cursor.
        """
        self._ensure_configured()

        payload: dict[str, Any] = {
            "client_id": self.client_id,
            "secret": self.secret,
            "access_token": access_token,
            "count": count,
        }
        if cursor:
            payload["cursor"] = cursor

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                res = await client.post(f"{self.base_url}/transactions/sync", json=payload)
                data = res.json()
                if res.status_code != 200:
                    raise PlaidError(
                        data.get("error_message", "Failed to sync transactions"),
                        error_code=data.get("error_code", "SYNC_FAILED"),
                        status_code=res.status_code,
                    )
                return data
            except httpx.RequestError as exc:
                raise PlaidError(f"Plaid network error: {exc}", error_code="NETWORK_ERROR")


plaid_client = PlaidClient()
