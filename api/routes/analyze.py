"""Bank statement CSV analysis endpoint; processes transactions in-memory without persistent writes."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional

from fastapi import APIRouter, File, Form, Header, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from services.agent.schema import LLMConfig
from services.agent.session_store import session_store
from services.calculations.balance_history import daily_balance_history
from services.ingestion.session_statement import append_entry, canonical_csv, manual_statement
from services.calculations.cash_analysis import calculate_cash_analysis, runway_days_for
from services.calculations.predictive_cash import (
    CashScenario,
    DetectedObligation,
    calculate_predictive_cash,
    detect_obligations,
    simulate_balances,
)
from services.calculations.receivables_ageing import calculate_receivables_ageing
from services.calculations.runway import calculate_cash_conversion_cycle
from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest
from services.ingestion.csv_parser import CSVIngestionError, parse_bank_csv, parse_multiple_bank_csv
from services.ingestion.invoice_parser import InvoiceIngestionError, parse_invoice_csv
from services.ingestion.pdf_parser import parse_pdf_statement
from services.ingestion.pdf_validator import PDFValidationError
from services.security.tenant_token import TenantTokenError, resolve_tenant_identity

router = APIRouter(prefix="/api/v1", tags=["Cash analysis"])
MAX_UPLOAD_BYTES = int(os.getenv("MAX_ANALYSIS_UPLOAD_BYTES", "10485760"))



class RejectedRowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    row_number: int
    reason_code: str


class AccountSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_name: str
    account_id: str
    start_date: str
    end_date: str
    closing_balance: str
    transaction_count: int


class ContraTransferSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outflow_tx_id: str
    inflow_tx_id: str
    amount: str
    outflow_account: str
    inflow_account: str
    transfer_date: str


class BalancePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str
    balance: str | None


class AccountHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str
    points: list[BalancePoint]


class RecurringObligation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["PAYROLL", "RENT", "DEBT_SERVICE"]
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    day_of_month: int = Field(ge=1, le=31)


class ForecastSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anchor_date: str
    has_projected_deficit: bool
    severity: str
    days_until_deficit: int | None
    projected_deficit_date: str | None
    projected_shortfall_amount: str
    recommended_bridge_amount: str
    primary_deficit_trigger: str | None
    detected_recurring_payroll: str | None
    detected_recurring_rent: str | None
    detected_recurring_debt: str | None


class CashAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: str
    accepted_count: int
    rejected_rows: list[RejectedRowResponse]
    current_balance: str
    net_period_change: str
    period_days: int
    average_daily_burn: str
    runway_days: int | None
    alert_threshold_days: int
    cash_status: Literal["CASH_NONPOSITIVE", "LOW_RUNWAY", "WATCH", "NO_BURN"]
    gross_inflows: str | None = None
    gross_outflows: str | None = None
    cash_conversion_cycle_days: int | None = None
    working_capital_status: Literal["WORKING_CAPITAL_TRAP", "BALANCED", "CASH_GENERATIVE"] | None = None
    working_capital_rationale: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    statement_age_days: int = 0
    analysis_mode: Literal["LIVE_OPERATING", "HISTORICAL_AUDIT"] = "LIVE_OPERATING"
    projected_depletion_date: str | None = None
    alert_boundary_date: str | None = None
    accounts_breakdown: list[AccountSummary] | None = None
    internal_transfers_excluded: str | None = None
    internal_transfers: list[ContraTransferSummary] | None = None
    calendar_gaps: list[str] | None = None
    has_overlaps_deduped: bool | None = None
    operational_inflows: str | None = None
    operational_outflows: str | None = None
    document_format: Literal["CSV", "PDF", "HYBRID", "MANUAL"] | None = None
    page_count: int | None = None
    normalized_csv: str | None = None
    # Chart data: what the statements show, and the forecast from the same engine as the deficit date.
    balance_history: list[BalancePoint] | None = None
    account_history: list[AccountHistory] | None = None
    recurring_obligations: list[RecurringObligation] | None = None
    forecast: ForecastSummary | None = None
    projection: list[BalancePoint] | None = None


FORECAST_DAYS = 90


def _record_in_session(session_id, tenant_token, authorization, tenant_id, build) -> Optional[JSONResponse]:
    """Writes the owner's entry into their chat session's statement; a forged token is refused (401)."""
    if not session_id:
        return None
    try:
        tenant = resolve_tenant_identity(x_tenant_token=tenant_token, authorization=authorization, x_tenant_id=tenant_id)
    except TenantTokenError as exc:
        return JSONResponse(status_code=401, content={"error": {"code": "INVALID_TOKEN", "message": str(exc)}})
    # Another tenant's session id gets nothing written to it; get_or_create would hand out a fresh session.
    rec = session_store.get(session_id)
    if rec is not None and rec.tenant_id != tenant:
        return None
    session_store.update_statement(session_id=session_id, csv_content=build(rec.csv_content if rec else None), tenant_id=tenant)
    return None


def _money_or_none(value: Decimal | None) -> str | None:
    return None if value is None else _format_money(value)


def _forecast_block(
    current_balance: Decimal,
    average_daily_burn: Decimal,
    anchor: date,
    obligations: list[DetectedObligation],
    scenario: CashScenario | None = None,
    days: int = FORECAST_DAYS,
) -> tuple[ForecastSummary, list[BalancePoint]]:
    """Forecast summary and daily projection from one simulation, so the chart and the deficit date agree."""
    res = calculate_predictive_cash(
        current_balance, average_daily_burn, [], anchor_date=anchor, projection_days=days,
        obligations=obligations, scenario=scenario,
    )
    points = [BalancePoint(date=anchor.isoformat(), balance=_format_money(current_balance))] + [
        BalancePoint(date=d.isoformat(), balance=_format_money(b))
        for d, b, _ in simulate_balances(current_balance, average_daily_burn, obligations, anchor, days, scenario)
    ]
    summary = ForecastSummary(
        anchor_date=anchor.isoformat(),
        has_projected_deficit=res.has_projected_deficit,
        severity=res.severity,
        days_until_deficit=res.days_until_deficit,
        projected_deficit_date=res.projected_deficit_date,
        projected_shortfall_amount=_format_money(res.projected_shortfall_amount),
        recommended_bridge_amount=_format_money(res.recommended_bridge_amount),
        primary_deficit_trigger=res.primary_deficit_trigger,
        detected_recurring_payroll=_money_or_none(res.detected_recurring_payroll),
        detected_recurring_rent=_money_or_none(res.detected_recurring_rent),
        detected_recurring_debt=_money_or_none(res.detected_recurring_debt),
    )
    return summary, points


def _obligations_out(obligations: list[DetectedObligation]) -> list[RecurringObligation]:
    return [
        RecurringObligation(category=ob.category, amount=ob.average_amount, day_of_month=ob.primary_day_of_month)  # type: ignore[arg-type]
        for ob in obligations
    ]


@router.post("/analyze", response_model=CashAnalysisResponse)
async def analyze_csv(
    request: Request,
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
    alert_threshold_days: int = Form(30, gt=0),
    dso_days: int | None = Form(None, ge=0),
    dpo_days: int | None = Form(None, ge=0),
    dio_days: int | None = Form(0, ge=0),
    as_of_date: date | None = Form(None),
    x_llm_config: Optional[str] = Header(default=None, alias="X-LLM-Config"),
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> CashAnalysisResponse | JSONResponse:
    if MAX_UPLOAD_BYTES <= 0:
        raise RuntimeError("MAX_ANALYSIS_UPLOAD_BYTES must be a positive integer")

    try:
        effective_tenant = resolve_tenant_identity(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
            x_tenant_id=x_tenant_id,
        )
    except TenantTokenError as exc:
        return JSONResponse(status_code=401, content={"error": {"code": "INVALID_TOKEN", "message": str(exc)}})

    effective_llm_config: LLMConfig | None = None
    if x_llm_config:
        try:
            parsed = json.loads(x_llm_config)
            effective_llm_config = LLMConfig(**parsed)
        except Exception:
            pass

    upload_list: list[UploadFile] = []
    try:
        form = await request.form()
        raw_items = form.getlist("files")
        if not raw_items:
            raw_items = form.getlist("file")
        for item in raw_items:
            if hasattr(item, "filename") and hasattr(item, "read"):
                upload_list.append(item)
    except Exception:
        pass

    if not upload_list:
        if files:
            upload_list.extend(files)
        elif file:
            upload_list.append(file)

    seen_names: set[str] = set()
    deduped_uploads: list[UploadFile] = []
    for u in upload_list:
        name = u.filename or "statement.csv"
        if name not in seen_names:
            seen_names.add(name)
            deduped_uploads.append(u)
    upload_list = deduped_uploads

    if not upload_list:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_HEADER", "message": "Statement upload is required."}},
        )

    file_contents: list[tuple[str, bytes]] = []
    total_bytes = 0
    pdf_pages_total = 0
    has_pdf = False
    has_csv = False
    normalized_csv_parts: list[str] = []

    for upload in upload_list:
        content = await upload.read(MAX_UPLOAD_BYTES + 1)
        total_bytes += len(content)
        if total_bytes > MAX_UPLOAD_BYTES or len(content) > MAX_UPLOAD_BYTES:
            return JSONResponse(
                status_code=413,
                content={"error": {"code": "UPLOAD_TOO_LARGE", "message": "Statement upload exceeds the configured size limit."}},
            )
        filename = upload.filename or "statement.csv"
        is_pdf = filename.lower().endswith(".pdf") or content.startswith(b"%PDF")
        if is_pdf:
            has_pdf = True
            try:
                pdf_res = parse_pdf_statement(content, tenant_id=effective_tenant)
                pdf_pages_total += pdf_res.page_count
                csv_bytes = pdf_res.csv_text.encode("utf-8")
                normalized_csv_parts.append(pdf_res.csv_text)
                file_contents.append((filename, csv_bytes))
            except PDFValidationError as exc:
                return JSONResponse(status_code=422, content={"error": {"code": exc.code, "message": str(exc)}})
        else:
            has_csv = True
            try:
                normalized_csv_parts.append(content.decode("utf-8", errors="replace"))
            except Exception:
                pass
            file_contents.append((filename, content))

    try:
        if len(file_contents) == 1:
            ingestion = parse_bank_csv(file_contents[0][1], llm_config=effective_llm_config)
        else:
            ingestion = parse_multiple_bank_csv(file_contents, llm_config=effective_llm_config)
    except CSVIngestionError as exc:
        return JSONResponse(status_code=422, content={"error": {"code": exc.code, "message": str(exc)}})

    result = calculate_cash_analysis(
        ingestion.accepted_rows,
        ingestion.rejected_rows,
        alert_threshold_days,
        as_of_date=as_of_date,
    )

    ccc_days, wc_status, wc_rationale = None, None, None
    if dso_days is not None and dpo_days is not None:
        ccc_days, wc_status, wc_rationale = calculate_cash_conversion_cycle(
            dso_days=dso_days,
            dpo_days=dpo_days,
            dio_days=dio_days or 0,
        )

    acc_breakdown: list[AccountSummary] | None = None
    contra_excluded: str | None = None
    contra_summaries: list[ContraTransferSummary] | None = None
    cal_gaps: list[str] | None = None
    has_deduped: bool | None = None
    op_inflows: str | None = None
    op_outflows: str | None = None

    if ingestion.treasury is not None:
        t = ingestion.treasury
        acc_breakdown = [
            AccountSummary(
                file_name=a.file_name,
                account_id=a.account_id,
                start_date=a.start_date.isoformat(),
                end_date=a.end_date.isoformat(),
                closing_balance=_format_money(a.closing_balance),
                transaction_count=a.transaction_count,
            )
            for a in t.accounts
        ]
        if t.internal_transfer_volume > Decimal("0.00"):
            contra_excluded = _format_money(t.internal_transfer_volume)
        if t.internal_transfers:
            contra_summaries = [
                ContraTransferSummary(
                    outflow_tx_id=cp.outflow_tx_id,
                    inflow_tx_id=cp.inflow_tx_id,
                    amount=_format_money(cp.amount),
                    outflow_account=cp.outflow_account,
                    inflow_account=cp.inflow_account,
                    transfer_date=cp.transfer_date.isoformat(),
                )
                for cp in t.internal_transfers
            ]
        if t.calendar_gaps:
            cal_gaps = t.calendar_gaps
        has_deduped = t.has_overlaps_deduped
        op_inflows = _format_money(t.operational_inflows)
        op_outflows = _format_money(t.operational_outflows)
    elif ingestion.accepted_rows:
        # One file is one account with no transfers to remove, so operational flows equal gross flows.
        rows_sorted = sorted(ingestion.accepted_rows, key=lambda r: (r.posted_on, r.row_number))
        acc_breakdown = [
            AccountSummary(
                file_name=file_contents[0][0],
                account_id="Account_1",
                start_date=rows_sorted[0].posted_on.isoformat(),
                end_date=rows_sorted[-1].posted_on.isoformat(),
                closing_balance=_format_money(rows_sorted[-1].closing_balance),
                transaction_count=len(rows_sorted),
            )
        ]
        op_inflows = _format_money(result.gross_inflows)
        op_outflows = _format_money(result.gross_outflows)

    # Balance history per account (the bank's own balances) and in total.
    if ingestion.treasury is not None and ingestion.treasury.account_rows:
        owner = {id(r): acc for acc, rs in ingestion.treasury.account_rows.items() for r in rs}
        history_rows = [r for rs in ingestion.treasury.account_rows.values() for r in rs]
    else:
        owner = {}
        history_rows = list(ingestion.accepted_rows)
    total_hist, per_account_hist = daily_balance_history(history_rows, lambda r: owner.get(id(r), "Account_1"))

    obligations = detect_obligations(ingestion.accepted_rows)
    forecast, projection = (None, None)
    if result.end_date:
        forecast, projection = _forecast_block(
            result.current_balance, result.average_daily_burn, date.fromisoformat(result.end_date), obligations
        )

    doc_format: Literal["CSV", "PDF", "HYBRID"] = "CSV"
    if has_pdf and has_csv:
        doc_format = "HYBRID"
    elif has_pdf:
        doc_format = "PDF"

    combined_csv = "\n".join(normalized_csv_parts) if normalized_csv_parts else None
    # The chat reads one statement in a fixed layout, built from the consolidated rows: raw files joined
    # end to end would mix accounts, and the last row's balance would be one account's, not the total.
    if x_session_id and ingestion.accepted_rows:
        combined_csv_for_session = canonical_csv(ingestion.accepted_rows, result.currency)
    else:
        combined_csv_for_session = None
    if combined_csv_for_session and x_session_id:
        try:
            session_store.update_statement(
                session_id=x_session_id,
                csv_content=combined_csv_for_session,
                tenant_id=effective_tenant,
            )
        except Exception:
            pass

    return CashAnalysisResponse(
        currency=result.currency,
        accepted_count=result.accepted_count,
        rejected_rows=[RejectedRowResponse(row_number=r.row_number, reason_code=r.reason_code) for r in result.rejected_rows],
        current_balance=_format_money(result.current_balance),
        net_period_change=_format_money(result.net_period_change),
        period_days=result.period_days,
        average_daily_burn=_format_money(result.average_daily_burn),
        runway_days=result.runway_days,
        alert_threshold_days=result.alert_threshold_days,
        cash_status=result.cash_status,
        gross_inflows=_format_money(result.gross_inflows),
        gross_outflows=_format_money(result.gross_outflows),
        cash_conversion_cycle_days=ccc_days,
        working_capital_status=wc_status,
        working_capital_rationale=wc_rationale,
        start_date=result.start_date,
        end_date=result.end_date,
        statement_age_days=result.statement_age_days,
        analysis_mode=result.analysis_mode,  # type: ignore[arg-type]
        projected_depletion_date=result.projected_depletion_date,
        alert_boundary_date=result.alert_boundary_date,
        accounts_breakdown=acc_breakdown,
        internal_transfers_excluded=contra_excluded,
        internal_transfers=contra_summaries,
        calendar_gaps=cal_gaps,
        has_overlaps_deduped=has_deduped,
        operational_inflows=op_inflows,
        operational_outflows=op_outflows,
        document_format=doc_format,
        page_count=pdf_pages_total if has_pdf else None,
        normalized_csv=combined_csv if has_pdf else None,
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


def _format_money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


class AgeingBucketModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    amount: str
    percentage: str
    invoice_count: int


class CustomerDebtorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_name: str
    total_open_balance: str
    current_amount: str
    overdue_amount: str
    max_days_overdue: int
    invoice_count: int
    share_of_total_ar: str
    oldest_unpaid_invoice: Optional[str] = None


class ReceivablesAgeingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: str
    accepted_count: int
    rejected_rows: list[RejectedRowResponse]
    as_of_date: str
    total_ar: str
    current_amount: str
    total_overdue: str
    overdue_ratio_pct: str
    weighted_average_days_overdue: str
    top_1_concentration_pct: str
    risk_tier: str
    summary_advisory: str
    buckets: dict[str, AgeingBucketModel]
    top_debtors: list[CustomerDebtorModel]
    recommended_actions: list[str]


@router.post("/analyze/invoices", response_model=ReceivablesAgeingResponse)
async def analyze_invoices_csv(
    request: Request,
    file: UploadFile | None = File(None),
    as_of_date: date | None = Form(None),
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> ReceivablesAgeingResponse | JSONResponse:
    """Parses accounts receivable invoices CSV and computes an AR aging schedule with risk advisory."""
    try:
        effective_tenant = resolve_tenant_identity(
            x_tenant_token=x_tenant_token,
            authorization=authorization,
            x_tenant_id=x_tenant_id,
        )
    except TenantTokenError as exc:
        return JSONResponse(status_code=401, content={"error": {"code": "INVALID_TOKEN", "message": str(exc)}})

    if file is None:
        form = await request.form()
        raw_file = form.get("file")
        if hasattr(raw_file, "filename") and hasattr(raw_file, "read"):
            file = raw_file  # type: ignore[assignment]

    if not file:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "MISSING_FILE", "message": "Invoice CSV upload is required."}},
        )

    content_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content_bytes) > MAX_UPLOAD_BYTES:
        return JSONResponse(
            status_code=413,
            content={"error": {"code": "UPLOAD_TOO_LARGE", "message": "Invoice upload exceeds size limit."}},
        )

    content_str = content_bytes.decode("utf-8", errors="replace")
    try:
        ingestion = parse_invoice_csv(content_str, tenant_id=effective_tenant)
    except InvoiceIngestionError as exc:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": exc.code, "message": str(exc)}},
        )

    if not ingestion.accepted_invoices:
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "NO_VALID_INVOICES", "message": "No valid invoice rows found in CSV."}},
        )

    res = calculate_receivables_ageing(ingestion.accepted_invoices, as_of_date=as_of_date)

    if x_session_id:
        try:
            session_store.update_invoices(
                session_id=x_session_id,
                invoices_csv=content_str,
                tenant_id=effective_tenant,
            )
        except Exception:
            pass

    return ReceivablesAgeingResponse(
        currency=ingestion.currency,
        accepted_count=len(ingestion.accepted_invoices),
        rejected_rows=[
            RejectedRowResponse(row_number=r.row_number, reason_code=r.reason_code)
            for r in ingestion.rejected_rows
        ],
        as_of_date=res.as_of_date.isoformat(),
        total_ar=_format_money(res.total_ar),
        current_amount=_format_money(res.current_amount),
        total_overdue=_format_money(res.total_overdue),
        overdue_ratio_pct=str(res.overdue_ratio_pct),
        weighted_average_days_overdue=str(res.weighted_average_days_overdue),
        top_1_concentration_pct=str(res.top_1_concentration_pct),
        risk_tier=res.risk_tier,
        summary_advisory=res.summary_advisory,
        buckets={
            b_key: AgeingBucketModel(
                label=b.label,
                amount=_format_money(b.amount),
                percentage=str(b.percentage),
                invoice_count=b.invoice_count,
            )
            for b_key, b in res.buckets.items()
        },
        top_debtors=[
            CustomerDebtorModel(
                customer_name=d.customer_name,
                total_open_balance=_format_money(d.total_open_balance),
                current_amount=_format_money(d.current_amount),
                overdue_amount=_format_money(d.overdue_amount),
                max_days_overdue=d.max_days_overdue,
                invoice_count=d.invoice_count,
                share_of_total_ar=str(d.share_of_total_ar),
                oldest_unpaid_invoice=d.oldest_unpaid_invoice,
            )
            for d in res.top_debtors[:10]
        ],
        recommended_actions=res.recommended_actions,
    )


class AccountBalanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: str = Field(min_length=1, max_length=80)
    balance: Decimal = Field(max_digits=18, decimal_places=4)


# Field bounds make bad input a 422 validation error instead of a 500 from a raised ValueError.
class CashAdjustmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_balance: Decimal = Field(max_digits=18, decimal_places=4)
    adjustment_type: Literal["INFLOW", "OUTFLOW", "SET_BALANCE"]
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    description: Optional[str] = Field(default=None, max_length=200)
    # None means the owner gave no burn: runway stays unknown rather than estimated.
    daily_burn: Optional[Decimal] = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    effective_date: Optional[date] = None
    alert_threshold_days: int = Field(default=30, gt=0)
    # Several accounts: the change lands on account_id (a new id opens an account) and the total is the sum.
    # Without them the adjustment applies to current_balance as one pooled balance.
    account_id: Optional[str] = Field(default=None, min_length=1, max_length=80)
    accounts: list[AccountBalanceIn] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _accounts_are_distinct(self) -> "CashAdjustmentRequest":
        ids = [a.account_id for a in self.accounts]
        if len(ids) != len(set(ids)):
            raise ValueError("each account may appear only once")
        if self.accounts and not self.account_id:
            raise ValueError("account_id is required when accounts are given")
        return self


class SummaryAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_balance: Decimal = Field(max_digits=18, decimal_places=4)
    monthly_burn: Optional[Decimal] = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    daily_burn: Optional[Decimal] = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    monthly_inflow: Optional[Decimal] = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    as_of_date: Optional[date] = None
    alert_threshold_days: int = Field(default=30, gt=0)
    account_name: Optional[str] = Field(default="Operating Account", max_length=80)


@router.post("/analyze/adjust", response_model=CashAnalysisResponse)
async def adjust_cash(
    payload: CashAdjustmentRequest,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> CashAnalysisResponse | JSONResponse:
    as_of = payload.effective_date or date.today()

    def apply(previous: Decimal) -> Decimal:
        if payload.adjustment_type == "SET_BALANCE":
            return payload.amount
        if payload.adjustment_type == "INFLOW":
            return previous + payload.amount
        return previous - payload.amount  # OUTFLOW; the Literal type admits nothing else

    balances: dict[str, Decimal] = {a.account_id: a.balance for a in payload.accounts}
    accounts_out: list[AccountSummary] | None = None
    if payload.account_id:
        previous = balances.get(payload.account_id, Decimal("0.00"))
        balances[payload.account_id] = apply(previous)
        new_balance = sum(balances.values(), Decimal("0.00"))
        net_change = balances[payload.account_id] - previous
        accounts_out = [
            AccountSummary(
                file_name="manual_entry",
                account_id=acc,
                start_date=as_of.isoformat(),
                end_date=as_of.isoformat(),
                closing_balance=_format_money(bal),
                transaction_count=1,
            )
            for acc, bal in balances.items()
        ]
    else:
        new_balance = apply(payload.current_balance)
        net_change = new_balance - payload.current_balance

    burn = (payload.daily_burn or Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    runway = runway_days_for(new_balance, burn)
    depletion_date = (as_of + timedelta(days=runway)).isoformat() if runway is not None else None
    alert_boundary_date = (as_of + timedelta(days=payload.alert_threshold_days)).isoformat()

    decision_req = DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={
            "eval_cash_status": True,
            "current_balance": float(new_balance),
            "average_daily_burn": float(burn),
            "runway_days": runway,
            "alert_threshold_days": payload.alert_threshold_days,
            "statement_age_days": 0,
        },
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    cash_status = decision_res.selected_choice

    forecast, projection = _forecast_block(new_balance, burn, as_of, [])
    gross_in = _format_money(payload.amount) if payload.adjustment_type == "INFLOW" else "0.00"

    # The chat answers from the session statement, so the entry is added there as a dated row.
    stored = _record_in_session(
        x_session_id, x_tenant_token, authorization, x_tenant_id,
        lambda existing: append_entry(
            existing, as_of, net_change, new_balance, payload.currency, payload.description or "", payload.daily_burn
        ) if existing else manual_statement(new_balance, payload.currency, as_of, payload.daily_burn),
    )
    if isinstance(stored, JSONResponse):
        return stored
    gross_out = _format_money(payload.amount) if payload.adjustment_type == "OUTFLOW" else "0.00"

    return CashAnalysisResponse(
        currency=payload.currency,
        accepted_count=1,
        rejected_rows=[],
        current_balance=_format_money(new_balance),
        net_period_change=_format_money(net_change),
        period_days=1,
        average_daily_burn=_format_money(burn),
        runway_days=runway,
        alert_threshold_days=payload.alert_threshold_days,
        cash_status=cash_status,
        gross_inflows=gross_in,
        gross_outflows=gross_out,
        start_date=as_of.isoformat(),
        end_date=as_of.isoformat(),
        statement_age_days=0,
        analysis_mode="LIVE_OPERATING",
        projected_depletion_date=depletion_date,
        alert_boundary_date=alert_boundary_date,
        accounts_breakdown=accounts_out,
        document_format="MANUAL",
        forecast=forecast,
        projection=projection,
    )


@router.post("/analyze/summary", response_model=CashAnalysisResponse)
async def analyze_summary(
    payload: SummaryAnalysisRequest,
    x_session_id: Optional[str] = Header(default=None, alias="X-Session-ID"),
    x_tenant_token: Optional[str] = Header(default=None, alias="X-Tenant-Token"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
) -> CashAnalysisResponse | JSONResponse:
    as_of = payload.as_of_date or date.today()

    if payload.daily_burn is not None:
        burn = payload.daily_burn.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif payload.monthly_burn is not None:
        if payload.monthly_inflow is not None:
            net_burn = max(Decimal("0.00"), payload.monthly_burn - payload.monthly_inflow)
            burn = (net_burn / Decimal("30")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            burn = (payload.monthly_burn / Decimal("30")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        burn = Decimal("0.00")

    runway = runway_days_for(payload.current_balance, burn)
    depletion_date = (as_of + timedelta(days=runway)).isoformat() if runway is not None else None
    alert_boundary_date = (as_of + timedelta(days=payload.alert_threshold_days)).isoformat()

    decision_req = DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={
            "eval_cash_status": True,
            "current_balance": float(payload.current_balance),
            "average_daily_burn": float(burn),
            "runway_days": runway,
            "alert_threshold_days": payload.alert_threshold_days,
            "statement_age_days": 0,
        },
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    cash_status = decision_res.selected_choice

    forecast, projection = _forecast_block(payload.current_balance, burn, as_of, [])
    # A typed balance replaces whatever statement the session held; the typed spend travels with it.
    declared = burn if (payload.daily_burn is not None or payload.monthly_burn is not None) else None
    stored = _record_in_session(
        x_session_id, x_tenant_token, authorization, x_tenant_id,
        lambda _existing: manual_statement(payload.current_balance, payload.currency, as_of, declared),
    )
    if isinstance(stored, JSONResponse):
        return stored
    acc_name = payload.account_name or "Operating Account"
    accounts = [
        AccountSummary(
            file_name="manual_entry",
            account_id=acc_name,
            start_date=as_of.isoformat(),
            end_date=as_of.isoformat(),
            closing_balance=_format_money(payload.current_balance),
            transaction_count=1,
        )
    ]

    return CashAnalysisResponse(
        currency=payload.currency,
        accepted_count=1,
        rejected_rows=[],
        current_balance=_format_money(payload.current_balance),
        net_period_change="0.00",
        period_days=30,
        average_daily_burn=_format_money(burn),
        runway_days=runway,
        alert_threshold_days=payload.alert_threshold_days,
        cash_status=cash_status,
        gross_inflows=_format_money(payload.monthly_inflow or Decimal("0.00")),
        gross_outflows=_format_money(payload.monthly_burn or Decimal("0.00")),
        start_date=as_of.isoformat(),
        end_date=as_of.isoformat(),
        statement_age_days=0,
        analysis_mode="LIVE_OPERATING",
        projected_depletion_date=depletion_date,
        alert_boundary_date=alert_boundary_date,
        accounts_breakdown=accounts,
        document_format="MANUAL",
        forecast=forecast,
        projection=projection,
    )


class OneOffInflow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: date
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=4)


class ScenarioRequest(BaseModel):
    """What-if levers on a known position. Stateless: the client sends the figures /analyze returned."""

    model_config = ConfigDict(extra="forbid")
    current_balance: Decimal = Field(max_digits=18, decimal_places=4)
    average_daily_burn: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    anchor_date: date
    obligations: list[RecurringObligation] = Field(default_factory=list, max_length=10)
    variable_cut_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2)
    extra_monthly_payroll: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    one_off_inflows: list[OneOffInflow] = Field(default_factory=list, max_length=20)
    days: int = Field(default=FORECAST_DAYS, ge=1, le=365)


class ScenarioResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    forecast: ForecastSummary
    projection: list[BalancePoint]


@router.post("/analyze/scenario", response_model=ScenarioResponse)
async def analyze_scenario(payload: ScenarioRequest) -> ScenarioResponse:
    """Re-runs the forecast with the owner's what-if levers; the same engine as the deficit date on /analyze."""
    obligations = [
        DetectedObligation(category=o.category, average_amount=o.amount, primary_day_of_month=o.day_of_month)
        for o in payload.obligations
    ]
    scenario = CashScenario(
        variable_cut_pct=payload.variable_cut_pct,
        extra_monthly_payroll=payload.extra_monthly_payroll,
        one_off_inflows=tuple((i.date, i.amount) for i in payload.one_off_inflows),
    )
    forecast, projection = _forecast_block(
        payload.current_balance, payload.average_daily_burn, payload.anchor_date, obligations, scenario, payload.days
    )
    return ScenarioResponse(forecast=forecast, projection=projection)
