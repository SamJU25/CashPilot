"""Plaid API Client with Automatic Sandbox Mock Fallback.
Handles Link token creation, public token exchange, account metadata,
and read-only transaction synchronization.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal
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
    Operates in live mode when PLAID_CLIENT_ID and PLAID_SECRET are configured;
    otherwise provides a zero-config deterministic sandbox simulator.
    """

    def __init__(
        self,
        client_id: str | None = None,
        secret: str | None = None,
        env: str | None = None,
    ):
        self.client_id = (client_id or os.getenv("PLAID_CLIENT_ID") or "").strip()
        self.secret = (secret or os.getenv("PLAID_SECRET") or "").strip()
        self.env = (env or os.getenv("PLAID_ENV") or "sandbox").strip().lower()
        self.base_url = PLAID_ENV_URLS.get(self.env, "https://sandbox.plaid.com")
        self._is_live = bool(self.client_id and self.secret)

    @property
    def is_live(self) -> bool:
        """True if configured with real Plaid API credentials."""
        return self._is_live

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "PLAID-CLIENT-ID": self.client_id,
            "PLAID-SECRET": self.secret,
        }

    async def create_link_token(
        self,
        client_user_id: str,
        client_name: str = "CashPilot",
        products: list[str] | None = None,
    ) -> dict[str, Any]:
        """Creates a Link token for the frontend Plaid Link modal."""
        if not self._is_live:
            # Deterministic sandbox token
            return {
                "link_token": f"link-sandbox-{uuid.uuid4().hex[:16]}",
                "expiration": (date.today() + timedelta(days=1)).isoformat() + "T00:00:00Z",
                "request_id": f"req-{uuid.uuid4().hex[:8]}",
                "sandbox_simulated": True,
            }

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
        """Exchanges public_token from the frontend modal for a permanent access_token."""
        if not self._is_live or public_token.startswith("public-sandbox-") or "mock" in public_token:
            item_id = f"item-sandbox-{uuid.uuid4().hex[:8]}"
            return {
                "access_token": f"access-sandbox-{uuid.uuid4().hex[:24]}",
                "item_id": item_id,
                "request_id": f"req-{uuid.uuid4().hex[:8]}",
                "sandbox_simulated": True,
            }

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
        """Retrieves read-only account balance and metadata."""
        if not self._is_live or access_token.startswith("access-sandbox-"):
            return [
                {
                    "account_id": "acc_svb_ops_01",
                    "name": "Operating Checking",
                    "official_name": "Silicon Valley Commercial Checking",
                    "type": "depository",
                    "subtype": "checking",
                    "balances": {
                        "available": 29922.08,
                        "current": 29922.08,
                        "iso_currency_code": "USD",
                    },
                    "institution_name": "Silicon Valley Bank",
                },
                {
                    "account_id": "acc_chase_payroll_02",
                    "name": "Payroll Account",
                    "official_name": "Chase Total Business Checking",
                    "type": "depository",
                    "subtype": "checking",
                    "balances": {
                        "available": 12450.00,
                        "current": 12450.00,
                        "iso_currency_code": "USD",
                    },
                    "institution_name": "Chase Bank",
                },
            ]

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
        if not self._is_live or access_token.startswith("access-sandbox-"):
            # Deterministic simulation with 60 days of business transactions
            today = date.today()
            simulated_txs = [
                # Account 1: SVB Operating
                {
                    "transaction_id": "tx_svb_001",
                    "account_id": "acc_svb_ops_01",
                    "amount": -15000.00,  # Plaid convention: negative is credit/inflow
                    "date": (today - timedelta(days=25)).isoformat(),
                    "name": "Client Acme Corp Inflow",
                    "category": ["Deposit", "Sales"],
                    "iso_currency_code": "USD",
                    "pending": False,
                },
                {
                    "transaction_id": "tx_svb_002",
                    "account_id": "acc_svb_ops_01",
                    "amount": 3200.00,  # Plaid convention: positive is debit/outflow
                    "date": (today - timedelta(days=20)).isoformat(),
                    "name": "AWS Cloud Hosting",
                    "category": ["Utilities", "Technology"],
                    "iso_currency_code": "USD",
                    "pending": False,
                },
                {
                    "transaction_id": "tx_svb_003",
                    "account_id": "acc_svb_ops_01",
                    "amount": 5000.00,  # Outflow: Inter-account transfer to Chase Payroll
                    "date": (today - timedelta(days=15)).isoformat(),
                    "name": "Transfer to Chase Payroll",
                    "category": ["Transfer", "Internal"],
                    "iso_currency_code": "USD",
                    "pending": False,
                },
                {
                    "transaction_id": "tx_svb_004",
                    "account_id": "acc_svb_ops_01",
                    "amount": -8500.00,  # Inflow
                    "date": (today - timedelta(days=8)).isoformat(),
                    "name": "Global Tech Subscription Revenue",
                    "category": ["Deposit", "Sales"],
                    "iso_currency_code": "USD",
                    "pending": False,
                },
                {
                    "transaction_id": "tx_svb_005",
                    "account_id": "acc_svb_ops_01",
                    "amount": 1450.00,  # Outflow
                    "date": (today - timedelta(days=2)).isoformat(),
                    "name": "Office Supplies & Software",
                    "category": ["Supplies"],
                    "iso_currency_code": "USD",
                    "pending": False,
                },
                # Account 2: Chase Payroll
                {
                    "transaction_id": "tx_chase_001",
                    "account_id": "acc_chase_payroll_02",
                    "amount": -5000.00,  # Inflow: Transfer received from SVB Operating
                    "date": (today - timedelta(days=15)).isoformat(),
                    "name": "Transfer from SVB Operating",
                    "category": ["Transfer", "Internal"],
                    "iso_currency_code": "USD",
                    "pending": False,
                },
                {
                    "transaction_id": "tx_chase_002",
                    "account_id": "acc_chase_payroll_02",
                    "amount": 4200.00,  # Outflow: Payroll run
                    "date": (today - timedelta(days=14)).isoformat(),
                    "name": "Gusto Payroll Disbursement",
                    "category": ["Payroll"],
                    "iso_currency_code": "USD",
                    "pending": False,
                },
            ]
            return {
                "added": simulated_txs,
                "modified": [],
                "removed": [],
                "next_cursor": "cur_sandbox_done",
                "has_more": False,
                "sandbox_simulated": True,
            }

        payload = {
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
