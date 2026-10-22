"""Plaid Transaction Ingestion and Multi-Account Treasury Synchronization.
Connects Plaid read-only streams into CashPilot's deterministic calculation engine.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from api.routes.analyze import (
    AccountHistory,
    AccountSummary,
    BalancePoint,
    CashAnalysisResponse,
    ContraTransferSummary,
    RejectedRowResponse,
    _forecast_block,
    _obligations_out,
)
from services.calculations.balance_history import daily_balance_history
from services.calculations.cash_analysis import calculate_cash_analysis
from services.calculations.predictive_cash import detect_obligations
from services.ingestion.csv_parser import DemoTransaction, IngestionResult
from services.ingestion.portfolio_consolidator import consolidate_multi_statement_treasury
from services.plaid.client import PlaidError, plaid_client
from services.plaid.storage import plaid_storage

logger = logging.getLogger(__name__)


def _format_money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _money_or_none(value: Decimal | None) -> str | None:
    return _format_money(value) if value is not None else None


async def sync_plaid_accounts_for_tenant(
    tenant_id: str,
    alert_threshold_days: int = 30,
) -> tuple[CashAnalysisResponse, list[dict[str, Any]]]:
    """Syncs all connected Plaid bank accounts for a tenant,
    reconstructs historical carry-forward balances, detects contra-transfers,
    and returns a typed CashAnalysisResponse.
    """
    items = plaid_storage.get_items(tenant_id)
    if not items:
        raise PlaidError("No connected bank accounts found for this tenant.", error_code="NO_ACCOUNTS")

    all_accounts: list[dict[str, Any]] = []
    account_file_results: list[tuple[str, IngestionResult]] = []

    for item in items:
        access_token = item["access_token"]
        inst_name = item.get("institution_name", "Connected Bank")

        try:
            accounts = await plaid_client.get_accounts(access_token)
            sync_res = await plaid_client.sync_transactions(access_token, cursor=item.get("cursor"))
        except Exception as exc:
            logger.warning("Failed to sync Plaid item %s: %s", item.get("item_id"), exc)
            continue

        plaid_storage.update_item_sync(
            tenant_id=tenant_id,
            item_id=item["item_id"],
            cursor=sync_res.get("next_cursor"),
            accounts=accounts,
        )

        for acc in accounts:
            acc["institution_name"] = inst_name
            all_accounts.append(acc)

        txs = sync_res.get("added", [])

        # Group transactions by account
        txs_by_acc: dict[str, list[dict[str, Any]]] = {}
        for tx in txs:
            txs_by_acc.setdefault(tx["account_id"], []).append(tx)

        # For accounts without transactions in this sync window, create a synthetic anchor from current balance
        for acc in accounts:
            acc_id = acc["account_id"]
            acc_name = f"{inst_name} - {acc.get('name', 'Checking')}"
            acc_txs = txs_by_acc.get(acc_id, [])

            current_bal = Decimal(str(acc.get("balances", {}).get("current", "0.00")))

            acc_currency = acc.get("balances", {}).get("iso_currency_code", "USD") or "USD"
            demo_rows: list[DemoTransaction] = []

            if acc_txs:
                # Sort ascending by date
                sorted_txs = sorted(acc_txs, key=lambda x: x.get("date", ""))
                # Plaid sign: positive is debit/outflow, negative is credit/inflow
                # CashPilot sign: positive is inflow, negative is outflow
                # Back-calculate closing balances from current balance
                net_change = sum((Decimal(str(-t["amount"])) for t in sorted_txs), Decimal("0.00"))
                running_bal = current_bal - net_change

                for i, t in enumerate(sorted_txs, start=1):
                    amt = Decimal(str(-t["amount"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    running_bal += amt
                    tx_date = date.fromisoformat(t["date"]) if isinstance(t["date"], str) else date.today()
                    demo_rows.append(
                        DemoTransaction(
                            row_number=i,
                            transaction_id=t.get("transaction_id", f"tx_{i}"),
                            posted_on=tx_date,
                            amount=amt,
                            currency=acc_currency,
                            description=t.get("name", "Bank Transaction"),
                            closing_balance=running_bal,
                        )
                    )
            else:
                # 1 synthetic anchor row representing current active balance
                demo_rows.append(
                    DemoTransaction(
                        row_number=1,
                        transaction_id=f"sync_anchor_{acc_id}",
                        posted_on=date.today(),
                        amount=Decimal("0.00"),
                        currency=acc_currency,
                        description=f"Current Balance {acc_name}",
                        closing_balance=current_bal,
                    )
                )

            ingest_result = IngestionResult(
                currency=acc.get("balances", {}).get("iso_currency_code", "USD") or "USD",
                accepted_rows=demo_rows,
                rejected_rows=[],
            )
            account_file_results.append((acc_name, ingest_result))

    if not account_file_results:
        raise PlaidError("Unable to extract account balances from connected banks.", error_code="EMPTY_ACCOUNTS")

    # Consolidate across all accounts with contra-transfer reconciliation
    treasury = consolidate_multi_statement_treasury(account_file_results)

    # Compute cash analysis metrics
    analysis_res = calculate_cash_analysis(
        rows=treasury.accepted_rows,
        rejected_rows=treasury.rejected_rows,
        alert_threshold_days=alert_threshold_days,
    )

    # Accounts breakdown
    acc_breakdown = [
        AccountSummary(
            file_name=profile.file_name,
            account_id=profile.account_id,
            start_date=profile.start_date.isoformat(),
            end_date=profile.end_date.isoformat(),
            closing_balance=_format_money(profile.closing_balance),
            transaction_count=profile.transaction_count,
        )
        for profile in treasury.accounts
    ]

    # Contra transfers
    contra_summaries = [
        ContraTransferSummary(
            outflow_tx_id=pair.outflow_tx_id,
            inflow_tx_id=pair.inflow_tx_id,
            amount=_format_money(pair.amount),
            outflow_account=pair.outflow_account,
            inflow_account=pair.inflow_account,
            transfer_date=pair.transfer_date.isoformat(),
        )
        for pair in treasury.internal_transfers
    ] if treasury.internal_transfers else None

    # History per account
    owner_map = {id(r): acc for acc, rs in treasury.account_rows.items() for r in rs}
    total_hist, per_account_hist = daily_balance_history(
        treasury.accepted_rows,
        lambda r: owner_map.get(id(r), treasury.accounts[0].account_id if treasury.accounts else "Account_1"),
    )

    obligations = detect_obligations(treasury.accepted_rows)

    # 30-day forecast and projection
    forecast, projection = (None, None)
    if analysis_res.end_date:
        forecast, projection = _forecast_block(
            analysis_res.current_balance,
            analysis_res.average_daily_burn,
            date.fromisoformat(analysis_res.end_date),
            obligations,
        )

    response = CashAnalysisResponse(
        currency=treasury.currency,
        accepted_count=len(treasury.accepted_rows),
        rejected_rows=[],
        current_balance=_format_money(treasury.consolidated_balance),
        net_period_change=_format_money(analysis_res.net_period_change),
        period_days=analysis_res.period_days,
        average_daily_burn=_format_money(analysis_res.average_daily_burn),
        runway_days=analysis_res.runway_days,
        alert_threshold_days=analysis_res.alert_threshold_days,
        cash_status=analysis_res.cash_status,
        gross_inflows=_format_money(treasury.total_gross_inflows),
        gross_outflows=_format_money(treasury.total_gross_outflows),
        start_date=analysis_res.start_date,
        end_date=analysis_res.end_date,
        statement_age_days=analysis_res.statement_age_days,
        analysis_mode=analysis_res.analysis_mode,  # type: ignore[arg-type]
        projected_depletion_date=analysis_res.projected_depletion_date,
        alert_boundary_date=analysis_res.alert_boundary_date,
        accounts_breakdown=acc_breakdown,
        internal_transfers_excluded=_format_money(treasury.internal_transfer_volume),
        internal_transfers=contra_summaries,
        calendar_gaps=treasury.calendar_gaps,
        has_overlaps_deduped=treasury.has_overlaps_deduped,
        operational_inflows=_format_money(treasury.operational_inflows),
        operational_outflows=_format_money(treasury.operational_outflows),
        document_format="CSV",
        balance_history=[BalancePoint(date=d.isoformat(), balance=_format_money(b)) for d, b in total_hist] or None,
        account_history=[
            AccountHistory(
                account_id=acc,
                points=[BalancePoint(date=d.isoformat(), balance=_money_or_none(b)) for d, b in line],
            )
            for acc, line in per_account_hist.items()
        ] or None,
        recurring_obligations=_obligations_out(obligations),
        forecast=forecast,
        projection=projection,
    )

    return response, all_accounts
