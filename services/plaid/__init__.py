"""Plaid Open Banking Integration for CashPilot.
Provides read-only bank account synchronization, real-time transaction ingestion,
and multi-account treasury aggregation.
"""

from services.plaid.client import PlaidClient, plaid_client
from services.plaid.storage import PlaidStorage, plaid_storage
from services.plaid.sync import sync_plaid_accounts_for_tenant

__all__ = [
    "PlaidClient",
    "plaid_client",
    "PlaidStorage",
    "plaid_storage",
    "sync_plaid_accounts_for_tenant",
]
