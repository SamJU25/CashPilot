"""Typed deterministic tool wrappers for the Autonomous AI Copilot Agent.

Adheres to:
1. Pure Decimal financial calculations (zero LLM approximations).
2. Row error provenance retention from CSV parsing.
3. Three-tier security staging isolation.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional, Sequence, Union

from services.calculations.cash_analysis import calculate_cash_analysis
from services.calculations.currency_registry import format_money
from services.calculations.cash_scenario import calculate_cash_scenario as calc_cash_scenario
from services.calculations.outflow_breakdown import calculate_outflow_breakdown
from services.calculations.predictive_cash import calculate_predictive_cash
from services.calculations.receivables_ageing import calculate_receivables_ageing
from services.calculations.runway import calculate_cash_conversion_cycle
from services.ingestion.invoice_parser import parse_invoice_csv, parse_invoices_from_dicts
from services.calculations.debt_service import (
    calculate_dscr as calc_dscr,
    calculate_fccr as calc_fccr,
    calculate_loan_amortization as calc_loan_amortization,
    calculate_factoring_proceeds as calc_factoring_proceeds,
    calculate_prudent_debt_capacity as calc_debt_capacity,
)
from services.calculations.unit_economics import (
    calculate_contribution_margin as calc_cm,
    calculate_break_even as calc_break_even,
    calculate_break_even_units as calc_be_units,
    calculate_margin_of_safety as calc_mos,
    calculate_operating_margins as calc_op_margins,
)
from services.calculations.working_capital import (
    calculate_wcr as calc_wcr,
    calculate_dso as calc_dso,
    calculate_dpo as calc_dpo,
    calculate_defensive_interval as calc_defensive_interval,
    calculate_operating_cash_flow_ratio as calc_ocf_ratio,
)
from services.calculations.concentration_risk import (
    calculate_client_concentration as calc_concentration,
    calculate_revenue_attrition_impact as calc_attrition,
    calculate_client_churn_impact as calc_client_churn,
)
from services.calculations.solvency import (
    calculate_current_ratio as calc_current_ratio,
    calculate_quick_ratio as calc_quick_ratio,
    calculate_debt_to_equity as calc_debt_to_equity,
    calculate_interest_coverage as calc_interest_coverage,
)
from services.calculations.trade_credit import (
    calculate_trade_credit_apr as calc_trade_credit_apr,
)
from services.calculations.currency import (
    calculate_currency_conversion as calc_currency_conversion,
    calculate_fx_exposure as calc_fx_exposure,
)
from services.calculations.treasury import (
    calculate_cash_drag as calc_cash_drag,
)
from services.calculations.dupont import (
    calculate_dupont_roe as calc_dupont_roe,
)
from services.calculations.lease_vs_buy import (
    calculate_lease_vs_buy as calc_lease_vs_buy,
)
from services.calculations.credit_distress import (
    calculate_altman_z_score as calc_altman_z,
    calculate_net_debt_to_ebitda as calc_net_debt_to_ebitda,
    calculate_debt_service_burden as calc_debt_service_burden,
)
from services.calculations.capital_efficiency import (
    calculate_roic as calc_roic,
    calculate_roa as calc_roa,
    calculate_eva as calc_eva,
)
from services.calculations.valuation import (
    calculate_free_cash_flow as calc_free_cash_flow,
    calculate_wacc as calc_wacc,
    calculate_enterprise_value_multiples as calc_ev_multiples,
    calculate_dcf_valuation as calc_dcf_valuation,
)
from services.calculations.saas_unit_economics import (
    calculate_ltv_cac as calc_ltv_cac,
    calculate_cac_payback as calc_cac_payback,
    calculate_net_revenue_retention as calc_nrr,
)
from services.blockchain.invoice_hasher import (
    calculate_canonical_invoice_hash,
    invoice_registry,
)
from services.ingestion.csv_parser import parse_bank_csv
from services.matcher.liquidity_matcher import (
    match_financing_options,
    underwrite_sme_transactions,
)
from services.security.staging_ledger import StagingRequest, staging_ledger


def _to_decimal(val: Any) -> Decimal:
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val).replace("$", "").replace(",", "").replace("%", "").strip())


def _format_money(val: Decimal) -> str:
    return f"{val:.2f}"


from services.ingestion.session_statement import declared_burn_applies, split_meta, strip_meta


def _normalize_statement_bytes(content_str: str) -> bytes:
    """Decodes string or base64 into raw bytes, converting PDF to canonical CSV bytes if needed."""
    if not content_str:
        return b""
    # The session statement may start with a settings line; parsers only ever see the CSV.
    content_str = strip_meta(content_str)
    trimmed = content_str.strip()
    raw_bytes = content_str.encode("utf-8")
    if trimmed.startswith("JVBERi0"):
        import base64
        try:
            decoded = base64.b64decode(trimmed)
            if decoded.startswith(b"%PDF"):
                raw_bytes = decoded
        except Exception:
            pass
    if raw_bytes.startswith(b"%PDF") or trimmed.startswith("%PDF"):
        from services.ingestion.pdf_parser import parse_pdf_statement
        pdf_res = parse_pdf_statement(raw_bytes)
        return pdf_res.csv_text.encode("utf-8")
    return raw_bytes


def tool_analyze_cash_flow(
    csv_content: str,
    alert_threshold_days: int = 30,
    target_horizon_days: Optional[int] = None,
    dso_days: Optional[int] = None,
    dpo_days: Optional[int] = None,
    dio_days: Optional[int] = None,
) -> Dict[str, Any]:
    """Ingest bank statement CSV and compute deterministic cash runway and predictive deficit metrics.

    Args:
        csv_content: Raw CSV bank statement text.
        alert_threshold_days: Minimum safe runway horizon in days.
        target_horizon_days: Optional arbitrary forecast target day count.
        dso_days: Optional Days Sales Outstanding.
        dpo_days: Optional Days Payable Outstanding.
        dio_days: Optional Days Inventory Outstanding.

    Returns:
        Structured dictionary containing balance, burn, runway, and forward predictive shortfall metrics.
    """
    raw_bytes = _normalize_statement_bytes(csv_content)
    ingestion = parse_bank_csv(raw_bytes)
    meta, _ = split_meta(csv_content or "")
    result = calculate_cash_analysis(
        ingestion.accepted_rows,
        ingestion.rejected_rows,
        alert_threshold_days=alert_threshold_days,
        declared_daily_burn=declared_burn_applies(meta, ingestion.accepted_rows),
    )
    prediction = calculate_predictive_cash(
        currency=result.currency,
        current_balance=result.current_balance,
        average_daily_burn=result.average_daily_burn,
        rows=ingestion.accepted_rows,
        projection_days=90,
        target_horizon_days=target_horizon_days,
    )

    ccc_days, ccc_status, ccc_rationale = None, None, None
    if dso_days is not None and dpo_days is not None:
        ccc_days, ccc_status, ccc_rationale = calculate_cash_conversion_cycle(
            dso_days=dso_days,
            dpo_days=dpo_days,
            dio_days=dio_days or 0,
        )

    return {
        "currency": result.currency,
        "accepted_count": result.accepted_count,
        "rejected_count": len(result.rejected_rows),
        "current_balance": str(result.current_balance),
        "net_period_change": str(result.net_period_change),
        "gross_inflows": str(result.gross_inflows),
        "gross_outflows": str(result.gross_outflows),
        "period_days": result.period_days,
        "average_daily_burn": str(result.average_daily_burn),
        "runway_days": result.runway_days,
        "cash_status": result.cash_status,
        "alert_threshold_days": result.alert_threshold_days,
        "has_projected_deficit": prediction.has_projected_deficit,
        "deficit_severity": prediction.severity,
        "days_until_deficit": prediction.days_until_deficit,
        "projected_deficit_date": prediction.projected_deficit_date,
        "projected_shortfall_amount": str(prediction.projected_shortfall_amount),
        "recommended_bridge_amount": str(prediction.recommended_bridge_amount),
        "target_horizon_days": prediction.target_horizon_days,
        "target_horizon_date": prediction.target_horizon_date,
        "forecast_target_balance": str(prediction.forecast_target_balance) if prediction.forecast_target_balance is not None else None,
        "confidence_tier": prediction.confidence_tier,
        "horizon_capped": prediction.horizon_capped,
        "advisory_note": prediction.advisory_note,
        "detected_recurring_rent": str(prediction.detected_recurring_rent) if prediction.detected_recurring_rent is not None else None,
        "detected_recurring_debt": str(prediction.detected_recurring_debt) if prediction.detected_recurring_debt is not None else None,
        "primary_deficit_trigger": prediction.primary_deficit_trigger,
        "predictive_explanation": prediction.explanation,
        "cash_conversion_cycle_days": ccc_days,
        "working_capital_status": ccc_status,
        "working_capital_rationale": ccc_rationale,
    }


def tool_annualized_statement_flows(csv_content: str) -> Dict[str, Any]:
    """
    Statement inflows, outflows and net cash flow scaled to a year by the statement's own period.
    A proxy for revenue, NOI or EBIT when the owner gives none; replies must show `note` beside it.
    """
    res = tool_analyze_cash_flow(csv_content)
    days = int(res.get("period_days") or 0)
    if days <= 0:
        raise ValueError("the statement covers no days")
    factor = Decimal("365") / Decimal(days)
    inflows = Decimal(str(res["gross_inflows"]))
    outflows = Decimal(str(res["gross_outflows"]))
    return {
        "inflows": (inflows * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "outflows": (outflows * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "net": (max(Decimal("0.00"), inflows - outflows) * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "period_days": days,
        "note": f" (estimated from {days} days of your bank statement, annualized; give the real figure for a precise result)",
    }


def tool_run_cash_scenario(
    csv_content: str,
    scenario: str,
    amount: Optional[Any] = None,
    percent: Optional[Any] = None,
    delay_days: Optional[int] = None,
) -> Dict[str, Any]:
    """Rerun runway and deficit on the statement for one what-if: INVOICE_DELAY, COST_CUT, NEW_EXPENSE or REVENUE_DROP."""
    ingestion = parse_bank_csv(_normalize_statement_bytes(csv_content))
    base = calculate_cash_analysis(ingestion.accepted_rows, ingestion.rejected_rows, alert_threshold_days=30)
    res = calc_cash_scenario(
        currency=ingestion.currency,
        current_balance=base.current_balance,
        net_period_change=base.net_period_change,
        gross_inflows=base.gross_inflows,
        period_days=base.period_days,
        rows=ingestion.accepted_rows,
        scenario=scenario,
        amount=_to_decimal(amount) if amount is not None else None,
        percent=_to_decimal(percent) if percent is not None else None,
        delay_days=int(delay_days) if delay_days is not None else None,
    )
    scn = res.scenario_deficit
    return {
        "scenario": res.scenario,
        "assumption": res.assumption,
        "current_balance": _format_money(base.current_balance),
        "amount": _format_money(_to_decimal(amount)) if amount is not None else None,
        "percent": str(percent) if percent is not None else None,
        "delay_days": delay_days,
        "baseline_daily_burn": _format_money(res.baseline_daily_burn),
        "scenario_daily_burn": _format_money(res.scenario_daily_burn),
        "baseline_runway_days": res.baseline_runway_days,
        "scenario_runway_days": res.scenario_runway_days,
        "runway_change_days": res.runway_change_days,
        "balance_during_delay": _format_money(res.balance_during_delay) if res.balance_during_delay is not None else None,
        "scenario_has_deficit": scn.has_projected_deficit,
        "scenario_days_until_deficit": scn.days_until_deficit,
        "scenario_deficit_date": scn.projected_deficit_date,
        "scenario_shortfall": _format_money(scn.projected_shortfall_amount),
        "scenario_severity": scn.severity,
    }


def tool_analyze_outflow_breakdown(csv_content: str) -> Dict[str, Any]:
    """Decomposes statement gross outflows into operational categories (Payroll, Facilities, Debt, Suppliers, Software, etc.)."""
    raw_bytes = _normalize_statement_bytes(csv_content)
    ingestion = parse_bank_csv(raw_bytes)
    res = calculate_outflow_breakdown(ingestion.accepted_rows)
    return {
        "gross_outflows": _format_money(res.gross_outflows),
        "period_days": res.period_days,
        "average_daily_outflow": _format_money(res.average_daily_outflow),
        "top_category": res.top_category,
        "top_category_amount": _format_money(res.top_category_amount),
        "top_category_percentage": str(res.top_category_percentage),
        "categories": [
            {
                "category": c.category,
                "total_amount": _format_money(c.total_amount),
                "percentage_of_outflows": str(c.percentage_of_outflows),
                "transaction_count": c.transaction_count,
                "average_transaction": _format_money(c.average_transaction),
                "largest_transaction": _format_money(c.largest_transaction),
            }
            for c in res.categories
        ],
    }


def tool_analyze_receivables_ageing(
    invoices: Optional[Any] = None,
    csv_content: Optional[str] = None,
    as_of_date: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Computes Accounts Receivable (AR) aging schedule, delinquency ratios, debtor concentration, and collections risk tier."""
    raw_invoices = invoices
    if raw_invoices is None and csv_content:
        raw_invoices = csv_content
    elif raw_invoices is None and session_id:
        from services.agent.session_store import session_store
        rec = session_store.get_or_create(session_id)
        if rec and rec.invoices_csv:
            raw_invoices = rec.invoices_csv

    if not raw_invoices:
        return {
            "error": "MISSING_INVOICE_DATA",
            "message": "No invoice records or CSV provided. Please upload an invoice CSV or supply invoice details.",
        }

    if isinstance(raw_invoices, str):
        ingest_res = parse_invoice_csv(raw_invoices)
        parsed_records = ingest_res.accepted_invoices
    elif isinstance(raw_invoices, list):
        ingest_res = parse_invoices_from_dicts(raw_invoices)
        parsed_records = ingest_res.accepted_invoices
    else:
        parsed_records = list(raw_invoices)
        ingest_res = None

    res = calculate_receivables_ageing(
        parsed_records, as_of_date=as_of_date, currency=ingest_res.currency if ingest_res else "USD"
    )

    return {
        "as_of_date": res.as_of_date.isoformat(),
        "total_ar": _format_money(res.total_ar),
        "current_amount": _format_money(res.current_amount),
        "total_overdue": _format_money(res.total_overdue),
        "overdue_ratio_pct": str(res.overdue_ratio_pct),
        "weighted_average_days_overdue": str(res.weighted_average_days_overdue),
        "top_1_concentration_pct": str(res.top_1_concentration_pct),
        "risk_tier": res.risk_tier,
        "summary_advisory": res.summary_advisory,
        "buckets": {
            b_key: {
                "label": b.label,
                "amount": _format_money(b.amount),
                "percentage": str(b.percentage),
                "invoice_count": b.invoice_count,
            }
            for b_key, b in res.buckets.items()
        },
        "top_debtors": [
            {
                "customer_name": d.customer_name,
                "total_open_balance": _format_money(d.total_open_balance),
                "current_amount": _format_money(d.current_amount),
                "overdue_amount": _format_money(d.overdue_amount),
                "max_days_overdue": d.max_days_overdue,
                "invoice_count": d.invoice_count,
                "share_of_total_ar": str(d.share_of_total_ar),
                "oldest_unpaid_invoice": d.oldest_unpaid_invoice,
            }
            for d in res.top_debtors[:5]
        ],
        "recommended_actions": res.recommended_actions,
    }


def tool_underwrite_credit(csv_content: str, nsf_count: int = 0) -> Dict[str, Any]:
    """Evaluate transactional data to generate WeBank underwriting dossier and matched credit lines.

    Args:
        csv_content: Raw CSV bank statement text.
        nsf_count: Non-sufficient funds incident count.

    Returns:
        Dossier scoring and filtered pre-qualified financing facilities with true APR.
    """
    raw_bytes = _normalize_statement_bytes(csv_content)
    ingestion = parse_bank_csv(raw_bytes)
    dossier = underwrite_sme_transactions(ingestion.accepted_rows, nsf_count=nsf_count)
    options = match_financing_options(dossier)

    return {
        "dossier": {
            "currency": dossier.currency,
            "daily_average_balance": _format_money(dossier.daily_average_balance),
            "transaction_count": dossier.transaction_count,
            "nsf_count": dossier.nsf_count,
            "risk_tier": dossier.risk_tier.value,
            "max_qualified_limit": _format_money(dossier.max_qualified_limit),
            "recommended_product_types": [p.value for p in dossier.recommended_product_types],
            "revenue_volatility_cv": _format_money(dossier.revenue_volatility_cv) if dossier.revenue_volatility_cv is not None else None,
            "volatility_tier": dossier.volatility_tier,
        },
        "matched_options": [
            {
                "provider": opt.provider,
                "product_type": opt.product_type.value,
                "facility_name": opt.facility_name,
                "max_amount": _format_money(opt.max_amount),
                "term_days": opt.term_days,
                "apr_percent": _format_money(opt.apr_percent),
                "is_predatory": opt.is_predatory,
                "suitability_score": opt.suitability_score,
                "requires_tier_3_hitl": opt.requires_tier_3_hitl,
            }
            for opt in options
        ],
    }


def tool_stage_financial_action(
    tenant_id: str,
    action_type: str,
    amount_cents: int,
    target_identifier: str,
) -> Dict[str, Any]:
    """Stage a financial action into the immutable staging queue (Tier 2).

    No money moves, and CashPilot never executes it: the owner prepares the request and sends it themselves.
    """
    request = StagingRequest(
        tenant_id=tenant_id,
        action_type=action_type,
        amount_cents=amount_cents,
        target_identifier=target_identifier,
    )
    intent = staging_ledger.stage_intent(request)
    return {
        "intent_id": intent.id,
        "tenant_id": intent.tenant_id,
        "action_type": intent.action_type,
        "amount_cents": intent.amount_cents,
        "target_identifier": intent.target_identifier,
        "status": intent.status,
    }


def tool_calculate_dscr(
    net_operating_income: Any,
    total_debt_service: Any,
) -> Dict[str, Any]:
    """Compute Debt Service Coverage Ratio (DSCR) and banking risk classification."""
    noi = _to_decimal(net_operating_income)
    service = _to_decimal(total_debt_service)
    dscr, status, rationale = calc_dscr(noi, service)
    return {
        "net_operating_income": _format_money(noi),
        "total_debt_service": _format_money(service),
        "dscr": str(dscr),
        "underwriting_status": status,
        "rationale": rationale,
    }


def tool_calculate_loan_amortization(
    principal: Any,
    annual_interest_rate_pct: Any,
    term_months: int,
    periods_elapsed: int = 0,
) -> Dict[str, Any]:
    """Calculate commercial loan monthly payment, total interest, and remaining balance."""
    p = _to_decimal(principal)
    raw_rate = _to_decimal(annual_interest_rate_pct)
    # Convert e.g. 8.5 to 0.085 if passed as percentage
    rate = raw_rate / Decimal("100") if raw_rate > Decimal("1.00") else raw_rate

    pmt, total_interest, remaining = calc_loan_amortization(
        principal=p,
        annual_interest_rate=rate,
        term_months=term_months,
        periods_elapsed=periods_elapsed,
    )
    total_paid = (pmt * Decimal(str(term_months))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "principal": _format_money(p),
        "annual_interest_rate_pct": _format_money(rate * Decimal("100")),
        "term_months": term_months,
        "monthly_payment": _format_money(pmt),
        "total_interest": _format_money(total_interest),
        "total_amount_paid": _format_money(total_paid),
        "remaining_balance": _format_money(remaining),
        "periods_elapsed": periods_elapsed,
    }


def tool_calculate_break_even(
    fixed_costs: Any,
    revenue: Optional[Any] = None,
    variable_costs: Optional[Any] = None,
    cm_ratio: Optional[Any] = None,
) -> Dict[str, Any]:
    """Calculate Break-Even Revenue ($), Contribution Margin Ratio, and Margin of Safety."""
    fc = _to_decimal(fixed_costs)
    if cm_ratio is not None:
        ratio = _to_decimal(cm_ratio)
        ratio = ratio / Decimal("100") if ratio > Decimal("1.00") else ratio
        cm_val = None
        rev = _to_decimal(revenue) if revenue is not None else None
        exact_ratio = ratio
    elif revenue is not None and variable_costs is not None:
        rev = _to_decimal(revenue)
        vc = _to_decimal(variable_costs)
        cm_val, ratio = calc_cm(rev, vc)
        exact_ratio = (rev - vc) / rev if rev > Decimal("0") else ratio
    else:
        raise ValueError("Either cm_ratio or (revenue and variable_costs) must be provided.")

    be_rev = calc_break_even(fc, exact_ratio)
    mos_dollars, mos_pct, mos_tier = None, None, None
    if rev is not None:
        mos_dollars, mos_pct, mos_tier = calc_mos(rev, be_rev)

    return {
        "fixed_costs": _format_money(fc),
        "contribution_margin_ratio": str(ratio),
        "break_even_revenue": _format_money(be_rev),
        "current_revenue": _format_money(rev) if rev is not None else None,
        "margin_of_safety_dollars": _format_money(mos_dollars) if mos_dollars is not None else None,
        "margin_of_safety_percent": str(mos_pct) if mos_pct is not None else None,
        "resilience_tier": mos_tier,
    }


def tool_calculate_factoring_proceeds(
    invoice_amount: Any,
    advance_rate_pct: Any,
    fee_rate_pct: Any,
    collection_days: int,
    ancillary_fees: Any = 0,
) -> Dict[str, Any]:
    """Calculate invoice factoring net cash advance, discount fee, and true annualized APR."""
    inv = _to_decimal(invoice_amount)
    # Always percentages: guessing fractions turned a 1% fee into 100%.
    adv_rate = _to_decimal(advance_rate_pct) / Decimal("100")
    fee_rate = _to_decimal(fee_rate_pct) / Decimal("100")
    ancillary = _to_decimal(ancillary_fees)

    advance, rebate, net_proceeds, apr, is_predatory = calc_factoring_proceeds(
        invoice_face_value=inv,
        advance_rate=adv_rate,
        discount_fee_rate=fee_rate,
        collection_days=collection_days,
        ancillary_fees=ancillary,
    )
    return {
        "invoice_face_value": _format_money(inv),
        "advance_rate_percent": _format_money(adv_rate * Decimal("100")),
        "advance_amount": _format_money(advance),
        "factoring_fee_amount": _format_money(inv * fee_rate),
        "rebate_amount": _format_money(rebate),
        "net_proceeds": _format_money(net_proceeds),
        "collection_days": collection_days,
        "true_apr_percent": str(apr),
        "is_predatory": is_predatory,
    }


def tool_calculate_client_concentration(
    csv_content: Optional[str] = None,
    client_inflows: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calculate customer revenue concentration and Herfindahl-Hirschman Index (HHI)."""
    inflow_dict: Dict[str, Decimal] = {}
    total_inflow = Decimal("0.00")

    if csv_content:
        raw_bytes = _normalize_statement_bytes(csv_content)
        ingestion = parse_bank_csv(raw_bytes)
        for row in ingestion.accepted_rows:
            if row.amount > Decimal("0.00"):
                key = (row.description or "Unlabeled Client").strip().title()
                inflow_dict[key] = inflow_dict.get(key, Decimal("0.00")) + row.amount
                total_inflow += row.amount
    elif client_inflows:
        for k, v in client_inflows.items():
            dec_v = _to_decimal(v)
            if dec_v > Decimal("0.00"):
                inflow_dict[k] = dec_v
                total_inflow += dec_v

    top_1, top_3, hhi, tier, assessment = calc_concentration(inflow_dict, total_inflow)
    return {
        "total_inflows_evaluated": _format_money(total_inflow),
        "client_count": len(inflow_dict),
        "top_1_client_percent": str(top_1),
        "top_3_clients_percent": str(top_3),
        "hhi_index": str(hhi),
        "concentration_tier": tier,
        "assessment": assessment,
    }


def tool_calculate_defensive_interval(
    quick_assets: Any,
    daily_operating_expenses: Any,
) -> Dict[str, Any]:
    """Calculate Defensive Interval Ratio (DIR) in days of liquid operational coverage."""
    qa = _to_decimal(quick_assets)
    burn = _to_decimal(daily_operating_expenses)
    dir_days, tier, rationale = calc_defensive_interval(qa, burn)
    return {
        "quick_assets": _format_money(qa),
        "daily_operating_expenses": _format_money(burn),
        "defensive_interval_days": str(dir_days),
        "liquidity_tier": tier,
        "rationale": rationale,
    }


def tool_calculate_fccr(
    ebitda: Any,
    fixed_charges: Any,
    total_debt_service: Any,
) -> Dict[str, Any]:
    """Calculate Fixed Charge Coverage Ratio (FCCR) and credit tier."""
    eb = _to_decimal(ebitda)
    fc = _to_decimal(fixed_charges)
    ds = _to_decimal(total_debt_service)
    fccr, tier, rationale = calc_fccr(eb, fc, ds)
    return {
        "ebitda": _format_money(eb),
        "fixed_charges": _format_money(fc),
        "total_debt_service": _format_money(ds),
        "fccr": str(fccr),
        "underwriting_tier": tier,
        "rationale": rationale,
    }


def tool_calculate_prudent_debt_capacity(
    net_operating_income: Any,
    target_dscr: Any = "1.25",
    annual_interest_rate_pct: Any = "8.5",
    term_years: int = 2,
    existing_annual_debt_service: Any = "0.00",
    ebitda: Optional[Any] = None,
    currency: str = "USD",
) -> Dict[str, Any]:
    """Calculate maximum prudent borrowing limit without violating DSCR and leverage covenants."""
    noi = _to_decimal(net_operating_income)
    dscr_val = _to_decimal(target_dscr)
    raw_rate = _to_decimal(annual_interest_rate_pct)
    rate = raw_rate / Decimal("100") if raw_rate > Decimal("1.00") else raw_rate
    service = _to_decimal(existing_annual_debt_service)
    eb = _to_decimal(ebitda) if ebitda is not None else None

    cap = calc_debt_capacity(
        net_operating_income=noi,
        target_dscr=dscr_val,
        existing_annual_debt_service=service,
        annual_interest_rate=rate,
        term_years=term_years,
        ebitda=eb,
    )
    return {
        "net_operating_income": _format_money(noi),
        "target_dscr": str(dscr_val),
        "annual_interest_rate_pct": _format_money(rate * Decimal("100")),
        "term_years": term_years,
        "existing_annual_debt_service": _format_money(service),
        "ebitda": _format_money(eb) if eb is not None else None,
        "maximum_prudent_debt_capacity": _format_money(cap),
        "advisory_summary": f"Maximum prudent borrowing capacity capped at {format_money(cap, currency)} to preserve a {dscr_val}x DSCR covenant.",
    }


def tool_calculate_wcr(
    accounts_receivable: Any,
    inventory: Any,
    accounts_payable: Any,
    annual_revenue: Optional[Any] = None,
    currency: str = "USD",
) -> Dict[str, Any]:
    """Calculate Working Capital Requirement (WCR = AR + Inventory - AP)."""
    ar = _to_decimal(accounts_receivable)
    inv = _to_decimal(inventory)
    ap = _to_decimal(accounts_payable)
    rev = _to_decimal(annual_revenue) if annual_revenue is not None else None
    wcr, days, status = calc_wcr(ar, inv, ap, annual_revenue=rev)
    rationale = f"Net working capital requirement is {format_money(wcr, currency)} ({status})."
    return {
        "accounts_receivable": _format_money(ar),
        "inventory": _format_money(inv),
        "accounts_payable": _format_money(ap),
        "working_capital_requirement": _format_money(wcr),
        "wcr_days_of_revenue": str(days) if days is not None else None,
        "liquidity_posture": status,
        "rationale": rationale,
    }


def tool_calculate_operating_cash_flow_ratio(
    operating_cash_flow: Any,
    current_liabilities: Any,
) -> Dict[str, Any]:
    """Calculate Operating Cash Flow Ratio (OCF / Current Liabilities)."""
    ocf = _to_decimal(operating_cash_flow)
    cl = _to_decimal(current_liabilities)
    ratio, tier, rationale = calc_ocf_ratio(ocf, cl)
    return {
        "operating_cash_flow": _format_money(ocf),
        "current_liabilities": _format_money(cl),
        "operating_cash_flow_ratio": str(ratio),
        "solvency_tier": tier,
        "rationale": rationale,
    }


def tool_calculate_break_even_units(
    fixed_costs: Any,
    unit_selling_price: Any,
    unit_variable_cost: Any,
    currency: str = "USD",
) -> Dict[str, Any]:
    """Calculate Break-Even Volume in physical units and unit contribution margin."""
    fc = _to_decimal(fixed_costs)
    p = _to_decimal(unit_selling_price)
    vc = _to_decimal(unit_variable_cost)
    be_units = calc_be_units(fc, p, vc)
    unit_cm = p - vc
    assessment = f"Must sell {int(be_units):,} units at {format_money(p, currency)} to fully cover {format_money(fc, currency)} fixed overhead."
    return {
        "fixed_costs": _format_money(fc),
        "unit_selling_price": _format_money(p),
        "unit_variable_cost": _format_money(vc),
        "unit_contribution_margin": _format_money(unit_cm),
        "break_even_units_required": int(be_units),
        "assessment": assessment,
    }


def tool_calculate_revenue_attrition_impact(
    current_annual_revenue: Any,
    current_annual_burn: Any,
    lost_client_annual_revenue: Any,
    currency: str = "USD",
) -> Dict[str, Any]:
    """Assess cash flow and burn expansion impact if a major customer churns."""
    rev = _to_decimal(current_annual_revenue)
    burn = _to_decimal(current_annual_burn)
    lost = _to_decimal(lost_client_annual_revenue)
    res = calc_client_churn(rev, burn, lost, currency=currency)
    return {
        "current_annual_revenue": _format_money(rev),
        "current_annual_burn": _format_money(burn),
        "lost_client_annual_revenue": _format_money(lost),
        "lost_revenue_share_percent": str(res["lost_revenue_share_percent"]),
        "projected_annual_burn": str(res["projected_annual_burn"]),
        "burn_expansion_rate_percent": str(res["burn_expansion_rate_percent"]),
        "severity": res["severity"],
        "recommendation": res["recommendation"],
    }


def tool_verify_invoice_hash(
    tax_id: str,
    buyer_id: str,
    invoice_num: str,
    amount_cents: int,
) -> Dict[str, Any]:
    """Compute canonical SHA-256 invoice hash and check double-financing on consortium registry."""
    inv_hash = calculate_canonical_invoice_hash(
        tax_id=tax_id,
        buyer_id=buyer_id,
        invoice_num=invoice_num,
        amount_cents=amount_cents,
    )
    status = invoice_registry.get_invoice_status(inv_hash)
    return {
        "tax_id": tax_id.strip().upper(),
        "buyer_id": buyer_id.strip().upper(),
        "invoice_num": invoice_num.strip().upper(),
        "amount_cents": amount_cents,
        "amount_dollars": _format_money(Decimal(amount_cents) / Decimal("100")),
        "invoice_hash": inv_hash,
        "consortium_status": status.value,
        "is_double_financing_risk": status.value != "UNREGISTERED",
    }


def tool_calculate_ccc(
    message: str = "",
    dso_days: Optional[int] = None,
    dpo_days: Optional[int] = None,
    dio_days: Optional[int] = None,
) -> Dict[str, Any]:
    """Calculates Cash Conversion Cycle (CCC = DSO + DIO - DPO) with trade terms."""
    import re
    dso = dso_days
    dpo = dpo_days
    dio = dio_days if dio_days is not None else 30

    if dso is None and message:
        m = re.search(r"\b(?:dso|receivables?|clients?|customers?)\D*?(\d{1,3})\s*[- ]*(?:day|days)\b", message, re.IGNORECASE)
        if m:
            dso = int(m.group(1))

    if dpo is None and message:
        m = re.search(r"\b(?:dpo|payables?|vendors?|suppliers?)\D*?(\d{1,3})\s*[- ]*(?:day|days)\b", message, re.IGNORECASE)
        if m:
            dpo = int(m.group(1))

    dso = dso if dso is not None else 45
    dpo = dpo if dpo is not None else 30
    dio = dio if dio is not None else 25

    ccc_days, status, rationale = calculate_cash_conversion_cycle(dso_days=dso, dio_days=dio, dpo_days=dpo)
    return {
        "dso_days": dso,
        "dio_days": dio,
        "dpo_days": dpo,
        "ccc_days": ccc_days,
        "cycle_classification": status,
        "rationale": rationale,
    }


def tool_calculate_predictive_cash(
    csv_content: str,
    forecast_horizon_days: int = 30,
) -> Dict[str, Any]:
    """Projects cash balance and identifies deficit points over custom horizons."""
    cf = tool_analyze_cash_flow(csv_content, target_horizon_days=forecast_horizon_days)
    return {
        "currency": cf["currency"],
        "severity": cf.get("deficit_severity", "SAFE"),
        "projected_shortfall": cf.get("projected_shortfall_amount", "0.00"),
        "shortfall_date": cf.get("projected_deficit_date"),
        "root_cause": cf.get("primary_deficit_trigger", "Operational cash burn"),
        "recommendation": cf.get("advisory_note") or "Maintain liquidity reserves",
        "has_projected_deficit": cf.get("has_projected_deficit", False),
        "days_until_deficit": cf.get("days_until_deficit"),
        "forecast_target_balance": cf.get("forecast_target_balance"),
    }


def tool_calculate_current_ratio(
    current_assets: Any,
    current_liabilities: Any,
) -> Dict[str, Any]:
    """Calculate Current Ratio (Current Assets / Current Liabilities) and working capital liquidity tier."""
    ca = _to_decimal(current_assets)
    cl = _to_decimal(current_liabilities)
    ratio, tier, rationale = calc_current_ratio(ca, cl)
    return {
        "current_assets": _format_money(ca),
        "current_liabilities": _format_money(cl),
        "current_ratio": str(ratio),
        "liquidity_tier": tier,
        "rationale": rationale,
    }


def tool_calculate_quick_ratio(
    current_assets: Any,
    inventory: Any,
    current_liabilities: Any,
    prepaid_expenses: Any = "0.00",
) -> Dict[str, Any]:
    """Calculate Quick Ratio / Acid Test and immediate liquidity readiness."""
    ca = _to_decimal(current_assets)
    inv = _to_decimal(inventory)
    cl = _to_decimal(current_liabilities)
    prep = _to_decimal(prepaid_expenses) if prepaid_expenses is not None else Decimal("0.00")
    ratio, tier, rationale = calc_quick_ratio(ca, inv, cl, prep)
    quick_assets = ca - inv - prep
    return {
        "current_assets": _format_money(ca),
        "inventory": _format_money(inv),
        "prepaid_expenses": _format_money(prep),
        "quick_assets": _format_money(quick_assets),
        "current_liabilities": _format_money(cl),
        "quick_ratio": str(ratio),
        "liquidity_tier": tier,
        "rationale": rationale,
    }


def tool_calculate_debt_to_equity(
    total_debt: Any,
    total_equity: Any,
) -> Dict[str, Any]:
    """Calculate Debt-to-Equity (D/E) Ratio and capital structure financial leverage tier."""
    debt = _to_decimal(total_debt)
    equity = _to_decimal(total_equity)
    ratio, tier, rationale = calc_debt_to_equity(debt, equity)
    return {
        "total_debt": _format_money(debt),
        "total_equity": _format_money(equity),
        "debt_to_equity_ratio": str(ratio),
        "leverage_tier": tier,
        "rationale": rationale,
    }


def tool_calculate_interest_coverage(
    ebit: Any,
    interest_expense: Any,
) -> Dict[str, Any]:
    """Calculate Interest Coverage Ratio (Times Interest Earned - TIE) and debt covenant risk tier."""
    eb = _to_decimal(ebit)
    ie = _to_decimal(interest_expense)
    ratio, tier, rationale = calc_interest_coverage(eb, ie)
    return {
        "ebit": _format_money(eb),
        "interest_expense": _format_money(ie),
        "interest_coverage_ratio": str(ratio),
        "covenant_tier": tier,
        "rationale": rationale,
    }


def tool_calculate_trade_credit_apr(
    discount_pct: Any,
    discount_days: int,
    net_days: int,
    invoice_amount: Optional[Any] = None,
    benchmark_borrowing_rate_pct: Optional[Any] = None,
) -> Dict[str, Any]:
    """Calculate implied Annual Percentage Rate (APR) of early payment trade terms (e.g. 2/10 Net 30)."""
    disc_pct = _to_decimal(discount_pct)
    inv_amt = _to_decimal(invoice_amount) if invoice_amount is not None else None
    bench_rate = _to_decimal(benchmark_borrowing_rate_pct) if benchmark_borrowing_rate_pct is not None else None
    return calc_trade_credit_apr(
        discount_pct=disc_pct,
        discount_days=int(discount_days),
        net_days=int(net_days),
        invoice_amount=inv_amt,
        benchmark_borrowing_rate_pct=bench_rate,
    )


def tool_calculate_cash_drag(
    current_balance: Any,
    monthly_burn: Optional[Any] = None,
    benchmark_annual_yield_pct: Any = "4.50",
    target_reserve_months: Any = "2.0",
    explicit_reserve_target: Optional[Any] = None,
    currency: str = "USD",
) -> Dict[str, Any]:
    """Calculate Treasury Cash Drag opportunity cost and idle cash yield loss against money market benchmarks."""
    cb = _to_decimal(current_balance)
    mb = _to_decimal(monthly_burn) if monthly_burn is not None else None
    yield_pct = _to_decimal(benchmark_annual_yield_pct) if benchmark_annual_yield_pct is not None else Decimal("4.50")
    reserve_months = _to_decimal(target_reserve_months) if target_reserve_months is not None else Decimal("2.0")
    explicit_res = _to_decimal(explicit_reserve_target) if explicit_reserve_target is not None else None
    return calc_cash_drag(
        current_balance=cb,
        monthly_burn=mb,
        benchmark_annual_yield_pct=yield_pct,
        target_reserve_months=reserve_months,
        explicit_reserve_target=explicit_res,
        currency=currency,
    )


def tool_calculate_dupont_roe(
    net_income: Any,
    revenue: Any,
    total_assets: Any,
    total_equity: Any,
) -> Dict[str, Any]:
    """Perform 3-Stage DuPont Analysis decomposing ROE into Net Margin, Asset Turnover, and Equity Multiplier."""
    ni = _to_decimal(net_income)
    rev = _to_decimal(revenue)
    assets = _to_decimal(total_assets)
    equity = _to_decimal(total_equity)
    return calc_dupont_roe(
        net_income=ni,
        revenue=rev,
        total_assets=assets,
        total_equity=equity,
    )


def tool_calculate_lease_vs_buy(
    purchase_price: Any,
    annual_lease_payment: Any,
    term_years: int,
    discount_rate_pct: Any,
    corporate_tax_rate_pct: Any = "21.0",
    estimated_salvage_value: Any = "0.00",
    annual_maintenance_if_bought: Any = "0.00",
    currency: str = "USD",
) -> Dict[str, Any]:
    """Evaluate equipment Lease vs. Buy Net Present Value (NPV) comparing after-tax cash flows and depreciation tax shields."""
    price = _to_decimal(purchase_price)
    lease_pay = _to_decimal(annual_lease_payment)
    disc_rate = _to_decimal(discount_rate_pct)
    tax_rate = _to_decimal(corporate_tax_rate_pct) if corporate_tax_rate_pct is not None else Decimal("21.0")
    salvage = _to_decimal(estimated_salvage_value) if estimated_salvage_value is not None else Decimal("0.00")
    maint = _to_decimal(annual_maintenance_if_bought) if annual_maintenance_if_bought is not None else Decimal("0.00")
    return calc_lease_vs_buy(
        purchase_price=price,
        annual_lease_payment=lease_pay,
        term_years=int(term_years),
        discount_rate_pct=disc_rate,
        corporate_tax_rate_pct=tax_rate,
        estimated_salvage_value=salvage,
        annual_maintenance_if_bought=maint,
        currency=currency,
    )


def tool_calculate_altman_z_score(
    working_capital: Any,
    retained_earnings: Any,
    ebit: Any,
    book_value_equity: Any,
    total_liabilities: Any,
    total_assets: Any,
    revenue: Any,
) -> Dict[str, Any]:
    """Calculate Altman Z'-Score for private manufacturing and service SMEs to evaluate credit distress and bankruptcy risk."""
    return calc_altman_z(
        working_capital=_to_decimal(working_capital),
        retained_earnings=_to_decimal(retained_earnings),
        ebit=_to_decimal(ebit),
        book_value_equity=_to_decimal(book_value_equity),
        total_liabilities=_to_decimal(total_liabilities),
        total_assets=_to_decimal(total_assets),
        revenue=_to_decimal(revenue),
    )


def tool_calculate_net_debt_to_ebitda(
    total_debt: Any,
    cash_and_equivalents: Any,
    ebitda: Any,
    currency: str = "USD",
) -> Dict[str, Any]:
    """Calculate Net Debt to EBITDA leverage ratio and benchmark credit risk."""
    return calc_net_debt_to_ebitda(
        total_debt=_to_decimal(total_debt),
        cash_and_equivalents=_to_decimal(cash_and_equivalents),
        ebitda=_to_decimal(ebitda),
        currency=currency,
    )


def tool_calculate_debt_service_burden(
    annual_debt_service: Any,
    gross_revenue: Any,
) -> Dict[str, Any]:
    """Calculate Debt Service Burden as a percentage of gross annual revenue."""
    return calc_debt_service_burden(
        annual_debt_service=_to_decimal(annual_debt_service),
        annual_revenue=_to_decimal(gross_revenue),
    )


def tool_calculate_roic(
    ebit: Any,
    total_debt: Any,
    total_equity: Any,
    cash_and_equivalents: Any = "0.00",
    tax_rate_pct: Any = "21.00",
    nopat: Optional[Any] = None,
) -> Dict[str, Any]:
    """Calculate Return on Invested Capital (ROIC) assessing operating return vs total invested capital."""
    return calc_roic(
        ebit=_to_decimal(ebit),
        total_debt=_to_decimal(total_debt),
        total_equity=_to_decimal(total_equity),
        cash_and_equivalents=_to_decimal(cash_and_equivalents) if cash_and_equivalents is not None else Decimal("0.00"),
        corporate_tax_rate_pct=_to_decimal(tax_rate_pct) if tax_rate_pct is not None else Decimal("21.00"),
    )


def tool_calculate_roa(
    net_income: Any,
    total_assets: Any,
    currency: str = "USD",
) -> Dict[str, Any]:
    """Calculate Return on Assets (ROA) evaluating net earnings efficiency per balance sheet asset dollar."""
    return calc_roa(
        net_income=_to_decimal(net_income),
        total_assets=_to_decimal(total_assets),
        currency=currency,
    )


def tool_calculate_eva(
    ebit: Any,
    invested_capital: Any,
    wacc_pct: Any = "9.00",
    tax_rate_pct: Any = "21.00",
    nopat: Optional[Any] = None,
    currency: str = "USD",
) -> Dict[str, Any]:
    """Calculate Economic Value Added (EVA) measuring surplus economic profit generated above cost of capital."""
    return calc_eva(
        ebit=_to_decimal(ebit),
        invested_capital=_to_decimal(invested_capital),
        wacc_pct=_to_decimal(wacc_pct) if wacc_pct is not None else Decimal("9.00"),
        corporate_tax_rate_pct=_to_decimal(tax_rate_pct) if tax_rate_pct is not None else Decimal("21.00"),
        currency=currency,
    )


def tool_calculate_free_cash_flow(
    operating_cash_flow: Any,
    capital_expenditures: Any,
    interest_expense: Any = "0.00",
    tax_rate_pct: Any = "21.00",
    net_debt_issued: Any = "0.00",
    currency: str = "USD",
) -> Dict[str, Any]:
    """Calculate Free Cash Flow to Firm (FCFF) and Free Cash Flow to Equity (FCFE)."""
    return calc_free_cash_flow(
        operating_cash_flow=_to_decimal(operating_cash_flow),
        capex=_to_decimal(capital_expenditures),
        interest_expense=_to_decimal(interest_expense) if interest_expense is not None else Decimal("0.00"),
        corporate_tax_rate_pct=_to_decimal(tax_rate_pct) if tax_rate_pct is not None else Decimal("21.00"),
        net_debt_issued=_to_decimal(net_debt_issued) if net_debt_issued is not None else Decimal("0.00"),
        currency=currency,
    )


def tool_calculate_wacc(
    equity_value: Any,
    total_debt: Any,
    cost_of_equity_pct: Any,
    pre_tax_cost_of_debt_pct: Any,
    corporate_tax_rate_pct: Any = "21.00",
) -> Dict[str, Any]:
    """Calculate Weighted Average Cost of Capital (WACC) with after-tax cost of debt shield."""
    return calc_wacc(
        equity_value=_to_decimal(equity_value),
        total_debt=_to_decimal(total_debt),
        cost_of_equity_pct=_to_decimal(cost_of_equity_pct),
        pre_tax_cost_of_debt_pct=_to_decimal(pre_tax_cost_of_debt_pct),
        corporate_tax_rate_pct=_to_decimal(corporate_tax_rate_pct) if corporate_tax_rate_pct is not None else Decimal("21.00"),
    )


def tool_calculate_enterprise_value(
    equity_value: Any,
    total_debt: Any,
    cash_and_equivalents: Any,
    ebitda: Optional[Any] = None,
    revenue: Optional[Any] = None,
    currency: str = "USD",
) -> Dict[str, Any]:
    """Calculate Enterprise Value (EV) and valuation multiples (EV/EBITDA, EV/Revenue)."""
    return calc_ev_multiples(
        equity_value=_to_decimal(equity_value),
        total_debt=_to_decimal(total_debt),
        cash_and_equivalents=_to_decimal(cash_and_equivalents),
        ebitda=_to_decimal(ebitda) if ebitda is not None else None,
        revenue=_to_decimal(revenue) if revenue is not None else None,
        currency=currency,
    )


def tool_calculate_dcf_valuation(
    projected_cash_flows: Sequence[Any],
    wacc_discount_rate_pct: Any,
    perpetual_growth_rate_pct: Any = "2.50",
    total_debt: Any = "0.00",
    cash_and_equivalents: Any = "0.00",
    currency: str = "USD",
) -> Dict[str, Any]:
    """Perform Discounted Cash Flow (DCF) enterprise valuation with Gordon Growth perpetual terminal value."""
    flows = [_to_decimal(f) for f in projected_cash_flows]
    return calc_dcf_valuation(
        projected_fcfs=flows,
        wacc_pct=_to_decimal(wacc_discount_rate_pct),
        terminal_growth_rate_pct=_to_decimal(perpetual_growth_rate_pct) if perpetual_growth_rate_pct is not None else Decimal("2.50"),
        total_debt=_to_decimal(total_debt) if total_debt is not None else Decimal("0.00"),
        cash_and_equivalents=_to_decimal(cash_and_equivalents) if cash_and_equivalents is not None else Decimal("0.00"),
        currency=currency,
    )


def tool_calculate_ltv_cac(
    arpu: Any = None,
    gross_margin_pct: Any = None,
    churn_rate_pct: Any = None,
    cac: Any = None,
    period: str = "ANNUAL",
    ltv: Any = None,
    currency: str = "USD",
) -> Dict[str, Any]:
    """Calculate Customer Lifetime Value (LTV) and LTV to CAC Ratio for subscription and recurring SME business models."""
    if ltv is not None:
        return calc_ltv_cac(cac=_to_decimal(cac), lifetime_value=_to_decimal(ltv), currency=currency)
    arpu_dec = _to_decimal(arpu)
    if period.upper() == "MONTHLY":
        annual_arpu = arpu_dec * Decimal("12")
    else:
        annual_arpu = arpu_dec
    return calc_ltv_cac(
        annual_arpu=annual_arpu,
        gross_margin_pct=_to_decimal(gross_margin_pct),
        annual_churn_rate_pct=_to_decimal(churn_rate_pct),
        cac=_to_decimal(cac),
        currency=currency,
    )


def tool_calculate_cac_payback(
    cac: Any,
    monthly_arpu: Any,
    gross_margin_pct: Any,
) -> Dict[str, Any]:
    """Calculate CAC Payback Period (Months) indicating how quickly gross margin recoups acquisition spend."""
    return calc_cac_payback(
        monthly_arpu=_to_decimal(monthly_arpu),
        gross_margin_pct=_to_decimal(gross_margin_pct),
        cac=_to_decimal(cac),
    )


def tool_calculate_nrr(
    starting_mrr: Any,
    expansion_mrr: Any = "0.00",
    contraction_mrr: Any = "0.00",
    churn_mrr: Any = "0.00",
    period: str = "ANNUAL",
    currency: str = "USD",
) -> Dict[str, Any]:
    """Calculate Net Revenue Retention (NRR) and Gross Revenue Retention (GRR) cohorts."""
    return calc_nrr(
        starting_arr=_to_decimal(starting_mrr),
        expansion_arr=_to_decimal(expansion_mrr) if expansion_mrr is not None else Decimal("0.00"),
        contraction_arr=_to_decimal(contraction_mrr) if contraction_mrr is not None else Decimal("0.00"),
        churn_arr=_to_decimal(churn_mrr) if churn_mrr is not None else Decimal("0.00"),
        currency=currency,
    )


def tool_convert_currency(
    amount: Any,
    from_currency: str = "USD",
    to_currency: str = "EUR",
    exchange_rate: Optional[Any] = None,
    spread_bps: Any = "0.00",
) -> Dict[str, Any]:
    """Deterministically convert an amount between any world currencies. If exchange_rate is omitted, fetches live market rate."""
    return calc_currency_conversion(
        amount=_to_decimal(amount),
        exchange_rate=_to_decimal(exchange_rate) if exchange_rate is not None and str(exchange_rate).strip() else None,
        from_currency=from_currency,
        to_currency=to_currency,
        spread_bps=_to_decimal(spread_bps) if spread_bps is not None else Decimal("0.00"),
    )


def tool_get_live_exchange_rate(
    from_currency: str,
    to_currency: str,
) -> Dict[str, Any]:
    """Fetch live spot foreign exchange (FX) market rate between any two world currencies."""
    from services.calculations.fx_rate_service import get_live_exchange_rate
    info = get_live_exchange_rate(from_currency=from_currency, to_currency=to_currency)
    return {
        "from_currency": info["from_currency"],
        "to_currency": info["to_currency"],
        "spot_rate": info["spot_rate"],
        "source": info["source"],
        "is_live_market": info["is_live_market"],
    }


def tool_calculate_fx_exposure(
    foreign_receivables: Any,
    foreign_payables: Any,
    base_currency: str = "USD",
    foreign_currency: str = "EUR",
    current_spot_rate: Optional[Any] = None,
    adverse_shock_pct: Any = "5.00",
) -> Dict[str, Any]:
    """Calculate Net Open Position (NOP) and potential cash flow loss under adverse FX volatility shock."""
    return calc_fx_exposure(
        foreign_receivables=_to_decimal(foreign_receivables),
        foreign_payables=_to_decimal(foreign_payables),
        base_currency=base_currency,
        foreign_currency=foreign_currency,
        current_spot_rate=_to_decimal(current_spot_rate) if current_spot_rate is not None and str(current_spot_rate).strip() else None,
        adverse_shock_pct=_to_decimal(adverse_shock_pct) if adverse_shock_pct is not None else Decimal("5.00"),
    )


def tool_evaluate_financial_math(expression: str) -> Dict[str, Any]:
    """Safely and deterministically evaluates an arithmetic expression using pure Decimal arithmetic.

    Prevents LLM math hallucinations. Strictly allows +, -, *, /, //, %, ** on numeric constants.
    """
    import ast
    import operator

    safe_ops = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def _eval(node: ast.AST) -> Decimal:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        elif isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            op_cls = type(node.op)
            if op_cls not in safe_ops:
                raise ValueError(f"Unsupported binary operator: {op_cls.__name__}")
            if op_cls in (ast.Div, ast.FloorDiv, ast.Mod) and right == Decimal("0"):
                raise ZeroDivisionError("Division by zero in financial expression.")
            res = safe_ops[op_cls](left, right)
            return Decimal(str(res))
        elif isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            op_cls = type(node.op)
            if op_cls not in safe_ops:
                raise ValueError(f"Unsupported unary operator: {op_cls.__name__}")
            res = safe_ops[op_cls](operand)
            return Decimal(str(res))
        raise ValueError(f"Security Policy: Expression contains prohibited AST node '{type(node).__name__}'.")

    clean_expr = expression.strip().replace(",", "")
    tree = ast.parse(clean_expr, mode="eval")
    val = _eval(tree)
    is_int = (val % Decimal("1") == Decimal("0"))
    return {
        "expression": expression,
        "result": str(int(val) if is_int else val.quantize(Decimal("0.0001"))),
        "is_integer": is_int,
        "integer_value": int(val) if is_int else None,
    }



# Advance rate used when factoring open invoices from the ageing schedule (the factoring card's example rate).
FACTORING_ADVANCE_RATE = Decimal("0.85")
# Supplier payments pushed back by this many days count as deferral capacity; two weeks is a common negotiated stretch.
SUPPLIER_DEFERRAL_DAYS = 14


def tool_build_bridge_plan(
    csv_content: str,
    invoices_csv: Optional[str] = None,
    stage: bool = False,
    tenant_id: str = "SME-DEFAULT",
) -> Dict[str, Any]:
    """Cheapest plan covering the projected shortfall plus buffer from supplier deferral, credit line and factoring.

    stage=True records the credit-line and factoring legs as Tier 2 proposals; deferral moves no money and is never staged.
    """
    from services.calculations.bridge_plan import FundingSource, calculate_bridge_plan

    cash = tool_analyze_cash_flow(csv_content)
    shortfall = _to_decimal(cash["projected_shortfall_amount"]) if cash["has_projected_deficit"] else Decimal("0.00")
    target = _to_decimal(cash["recommended_bridge_amount"]) if cash["has_projected_deficit"] else Decimal("0.00")

    sources = []
    if target > 0:
        options = [o for o in tool_underwrite_credit(csv_content)["matched_options"] if not o["is_predatory"]]
        for opt in options:
            if opt["product_type"] == "WORKING_CAPITAL_LINE":
                sources.append(FundingSource("DRAW_CREDIT_LINE", opt["facility_name"], _to_decimal(opt["max_amount"]),
                                             _to_decimal(opt["apr_percent"]), int(opt["term_days"]), "DRAW_CREDIT_LINE"))
            elif opt["product_type"] == "INVOICE_FACTORING":
                capacity = _to_decimal(opt["max_amount"])
                if invoices_csv:
                    ageing = tool_analyze_receivables_ageing(csv_content=invoices_csv)
                    if "error" not in ageing:
                        capacity = (_to_decimal(ageing["current_amount"]) * FACTORING_ADVANCE_RATE).quantize(Decimal("0.01"))
                sources.append(FundingSource("FACTOR_INVOICE", opt["facility_name"], capacity,
                                             _to_decimal(opt["apr_percent"]), int(opt["term_days"]), "FACTOR_INVOICE"))
        breakdown = tool_analyze_outflow_breakdown(csv_content)
        supplier = next((c for c in breakdown["categories"] if c["category"] == "Suppliers & Inventory"), None)
        if supplier:
            daily = _to_decimal(supplier["total_amount"]) / Decimal(breakdown["period_days"])
            sources.append(FundingSource("SUPPLIER_DEFERRAL", "Supplier payment deferral",
                                         (daily * SUPPLIER_DEFERRAL_DAYS).quantize(Decimal("0.01")), Decimal("0.00"),
                                         SUPPLIER_DEFERRAL_DAYS, None))

    plan = calculate_bridge_plan(shortfall, target, sources)
    staged = []
    if stage:
        for leg in plan.legs:
            if leg.source.stage_action:
                staged.append(tool_stage_financial_action(
                    tenant_id=tenant_id,
                    action_type=leg.source.stage_action,
                    amount_cents=int(leg.amount * 100),
                    target_identifier=leg.source.name,
                ))
    return {
        "has_shortfall": shortfall > 0,
        "deficit_date": cash["projected_deficit_date"],
        "shortfall": _format_money(plan.shortfall),
        "buffer": _format_money(plan.buffer),
        "target": _format_money(plan.target),
        "legs": [
            {
                "action": leg.source.kind,
                "source": leg.source.name,
                "amount": _format_money(leg.amount),
                "apr_percent": _format_money(leg.source.apr_percent),
                "term_days": leg.source.term_days,
                "cost": _format_money(leg.cost),
                "stageable": leg.source.stage_action is not None,
            }
            for leg in plan.legs
        ],
        "total_cost": _format_money(plan.total_cost),
        "uncovered": _format_money(plan.uncovered),
        "staged": staged,
    }
