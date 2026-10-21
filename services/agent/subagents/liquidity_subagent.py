"""SME CFO Diagnostician & Liquidity Subagent.

Specializes in:
1. Historical bank statement cash flow diagnostics (Balance, Burn, Runway, DAB).
2. Working Capital Requirement (WCR = Receivables + Inventory - Payables).
3. Cash Conversion Cycle (CCC = DSO + DIO - DPO).
4. Defensive Interval Ratio (DIR) & Operating Cash Flow Ratio (OCF).
5. Natural conversational follow-ups on liquidity reserves and cash status.
6. What-if cash scenarios (late invoice, cost cut, new cost, revenue drop) rerun on the statement.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from services.calculations.currency_registry import format_amount, format_money
from services.agent.param_extractor import (
    extract_cash_drag_params,
    extract_cash_scenario_params,
    extract_currency_conversion_params,
    extract_current_ratio_params,
    extract_defensive_interval_params,
    extract_free_cash_flow_params,
    extract_fx_exposure_params,
    extract_ocf_ratio_params,
    extract_quick_ratio_params,
    extract_receivables_ageing_params,
    extract_trade_credit_params,
    extract_wcr_params,
)
from services.agent.schema import (
    AgentActionProposal,
    AgentChatRequest,
    AgentMetricsSummary,
    CopilotResponse,
)
from services.agent.trace import traced_agent
from services.agent.tools import (
    tool_analyze_cash_flow,
    tool_analyze_outflow_breakdown,
    tool_analyze_receivables_ageing,
    tool_calculate_cash_drag,
    tool_calculate_ccc,
    tool_calculate_current_ratio,
    tool_calculate_defensive_interval,
    tool_calculate_free_cash_flow,
    tool_calculate_fx_exposure,
    tool_calculate_operating_cash_flow_ratio,
    tool_calculate_quick_ratio,
    tool_calculate_trade_credit_apr,
    tool_calculate_wcr,
    tool_convert_currency,
    tool_build_bridge_plan,
    tool_run_cash_scenario,
)
from services.agent.prompts import (
    get_missing_param_guidance,
    get_missing_statement_guidance,
    is_question,
    resolve_subagent_routing,
)


def _ratio_display(ratio: str) -> str:
    # Calculators return 999.00 when liabilities are zero; "999.00x" reads as a real ratio.
    return "Not meaningful (no current liabilities)" if str(ratio) == "999.00" else f"{ratio}x"


@traced_agent("liquidity")
class LiquiditySubagent:
    """Specialist subagent for working capital, operational cash flows, and liquidity diagnostics."""

    @staticmethod
    def can_handle(sub_intent: Optional[str]) -> bool:
        if not sub_intent:
            return False
        return resolve_subagent_routing(sub_intent) == "LiquiditySubagent"


    @classmethod
    def handle_sub_intent(
        cls,
        sub_intent: str,
        request: AgentChatRequest,
        effective_csv: Optional[str],
        enrich_fn: Callable[[str, str], str],
        allow_staging: bool = False,
        currency: str = "USD",
    ) -> Optional[CopilotResponse]:
        """Dispatches liquidity and working capital calculations to specialized tools."""
        # 1. Working Capital Requirement (WCR)
        if sub_intent == "WCR":
            p_dict = extract_wcr_params(request.message, history=request.history)
            ar = p_dict["accounts_receivable"]
            inv = p_dict["inventory"]
            ap = p_dict["accounts_payable"]

            if ar is not None and inv is not None and ap is not None:
                res = tool_calculate_wcr(accounts_receivable=ar, inventory=inv, accounts_payable=ap, currency=currency)
                base_reply = (
                    f"### Working Capital Requirement (WCR) Audit\n\n"
                    f"- **Accounts Receivable (AR)**: {format_money(res['accounts_receivable'], currency)}\n"
                    f"- **Inventory**: {format_money(res['inventory'], currency)}\n"
                    f"- **Accounts Payable (AP)**: {format_money(res['accounts_payable'], currency)}\n"
                    f"- **Net Working Capital Requirement**: {format_money(res['working_capital_requirement'], currency)}\n"
                    f"- **Liquidity Posture**: `{res['liquidity_posture']}`\n"
                    f"- **Structural Analysis**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("WCR"), prompt_type="concept", calculation="WCR"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 2. Operating Cash Flow (OCF) Ratio
        if sub_intent == "OCF_RATIO":
            p_dict = extract_ocf_ratio_params(request.message, history=request.history)
            ocf = p_dict["operating_cash_flow"]
            cl = p_dict["current_liabilities"]

            if ocf is not None and cl is not None:
                res = tool_calculate_operating_cash_flow_ratio(operating_cash_flow=ocf, current_liabilities=cl)
                base_reply = (
                    f"### Operating Cash Flow (OCF) Ratio Assessment\n\n"
                    f"- **Operating Cash Flow**: {format_money(res['operating_cash_flow'], currency)}\n"
                    f"- **Current Liabilities**: {format_money(res['current_liabilities'], currency)}\n"
                    f"- **Operating Cash Flow Ratio**: {res['operating_cash_flow_ratio']}x\n"
                    f"- **Solvency Classification**: `{res['solvency_tier']}`\n"
                    f"- **Evaluation**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("OCF_RATIO"), prompt_type="concept", calculation="OCF_RATIO"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 3. Defensive Interval Ratio (DIR)
        if sub_intent == "DEFENSIVE_INTERVAL":
            p_dict = extract_defensive_interval_params(request.message, history=request.history)
            qa = p_dict["quick_assets"]
            burn = p_dict["daily_operating_expenses"]
            metrics = None

            if (qa is None or burn is None) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    if qa is None:
                        qa = Decimal(str(cash_res["current_balance"]))
                    if burn is None:
                        burn = Decimal(str(cash_res["average_daily_burn"]))
                    metrics = AgentMetricsSummary(
                        current_balance=cash_res["current_balance"],
                        net_period_change=cash_res["net_period_change"],
                        average_daily_burn=cash_res["average_daily_burn"],
                        runway_days=cash_res["runway_days"],
                        cash_status=cash_res["cash_status"],
                        gross_inflows=cash_res.get("gross_inflows"),
                        gross_outflows=cash_res.get("gross_outflows"),
                    )
                except Exception:
                    pass

            if qa is not None and burn is not None:
                res = tool_calculate_defensive_interval(quick_assets=qa, daily_operating_expenses=burn)
                tier = res.get("resilience_tier") or res.get("liquidity_tier") or "MODERATE"
                advisory = res.get("summary") or res.get("rationale") or ""
                base_reply = (
                    f"### Defensive Interval Ratio (DIR) Liquidity Audit\n\n"
                    f"- **Liquid Quick Assets**: {format_money(res['quick_assets'], currency)}\n"
                    f"- **Daily Operating Burn Rate**: {format_money(res['daily_operating_expenses'], currency)}/day\n"
                    f"- **Defensive Survival Horizon**: {res['defensive_interval_days']} days\n"
                    f"- **Buffer Assessment Tier**: `{tier}`\n"
                    f"- **Advisory Assessment**: {advisory}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    metrics=metrics,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("DEFENSIVE_INTERVAL"), prompt_type="concept", calculation="DEFENSIVE_INTERVAL"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 4. Cash Conversion Cycle (CCC)
        if sub_intent == "WORKING_CAPITAL":
            if effective_csv:
                return None
            ccc_metrics = tool_calculate_ccc(request.message)
            ccc_summary = (
                f"- **Days Sales Outstanding (DSO)**: {ccc_metrics['dso_days']} days\n"
                f"- **Days Inventory Outstanding (DIO)**: {ccc_metrics['dio_days']} days\n"
                f"- **Days Payables Outstanding (DPO)**: {ccc_metrics['dpo_days']} days\n"
                f"- **Net Cash Conversion Cycle (CCC)**: {ccc_metrics['ccc_days']} days\n"
                f"- **Diagnosis**: `{ccc_metrics['cycle_classification']}` — {ccc_metrics['rationale']}"
            )
            base_reply = (
                f"Working capital cycle audit complete:\n\n{ccc_summary}\n\n"
                "Accelerating customer collections or stretching trade payables directly releases trapped cash."
            )
            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 5. Current Ratio
        if sub_intent == "CURRENT_RATIO":
            p_dict = extract_current_ratio_params(request.message, history=request.history)
            ca = p_dict["current_assets"]
            cl = p_dict["current_liabilities"]

            if (ca is None) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    ca = Decimal(str(cash_res["current_balance"]))
                except Exception:
                    pass

            if ca is not None and cl is not None:
                res = tool_calculate_current_ratio(current_assets=ca, current_liabilities=cl)
                base_reply = (
                    f"### Current Ratio Liquidity Audit\n\n"
                    f"- **Current Assets**: {format_money(res['current_assets'], currency)}\n"
                    f"- **Current Liabilities**: {format_money(res['current_liabilities'], currency)}\n"
                    f"- **Current Ratio**: {_ratio_display(res['current_ratio'])}\n"
                    f"- **Working Capital Solvency**: `{res['liquidity_tier']}`\n"
                    f"- **Evaluation**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("CURRENT_RATIO"), prompt_type="concept", calculation="CURRENT_RATIO"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 6. Quick Ratio (Acid Test)
        if sub_intent == "QUICK_RATIO":
            p_dict = extract_quick_ratio_params(request.message, history=request.history)
            ca = p_dict["current_assets"]
            inv = p_dict["inventory"]
            cl = p_dict["current_liabilities"]
            prep = p_dict["prepaid_expenses"]

            if (ca is None) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    ca = Decimal(str(cash_res["current_balance"]))
                except Exception:
                    pass

            if ca is not None and cl is not None:
                res = tool_calculate_quick_ratio(
                    current_assets=ca,
                    inventory=inv,
                    current_liabilities=cl,
                    prepaid_expenses=prep,
                )
                base_reply = (
                    f"### Quick Ratio (Acid Test) Audit\n\n"
                    f"- **Current Assets**: {format_money(res['current_assets'], currency)}\n"
                    f"- **Inventory Excluded**: {format_money(res['inventory'], currency)}\n"
                    f"- **Quick Liquid Assets**: {format_money(res['quick_assets'], currency)}\n"
                    f"- **Current Liabilities**: {format_money(res['current_liabilities'], currency)}\n"
                    f"- **Quick Ratio**: {_ratio_display(res['quick_ratio'])}\n"
                    f"- **Immediate Liquidity Tier**: `{res['liquidity_tier']}`\n"
                    f"- **Acid-Test Assessment**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("QUICK_RATIO"), prompt_type="concept", calculation="QUICK_RATIO"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 7. Trade Credit Early Payment Discount
        if sub_intent == "TRADE_CREDIT":
            p_dict = extract_trade_credit_params(request.message, history=request.history)
            disc_pct = p_dict["discount_pct"]
            disc_days = p_dict["discount_days"]
            net_days = p_dict["net_days"]
            inv_amt = p_dict["invoice_amount"]
            bench_rate = p_dict["benchmark_borrowing_rate_pct"]

            if disc_pct is not None and disc_days is not None and net_days is not None:
                res = tool_calculate_trade_credit_apr(
                    discount_pct=disc_pct,
                    discount_days=disc_days,
                    net_days=net_days,
                    invoice_amount=inv_amt,
                    benchmark_borrowing_rate_pct=bench_rate,
                )
                savings_line = (
                    f"- **Gross Early Payment Savings**: {format_money(res['discount_dollar_savings'], currency)}\n"
                    if res.get("discount_dollar_savings")
                    else ""
                )
                borrow_cost_line = (
                    f"- **Credit Facility Borrowing Cost**: {format_money(res['borrowing_cost_dollars'], currency)}\n"
                    if res.get("borrowing_cost_dollars")
                    else ""
                )
                net_benefit_line = (
                    f"- **Net Financial Benefit**: {format_money(res['net_benefit_dollars'], currency)}\n"
                    if res.get("net_benefit_dollars")
                    else ""
                )

                base_reply = (
                    f"### Trade Credit Terms Evaluation ({res['discount_pct']}%/{res['discount_days']} Net {res['net_days']})\n\n"
                    f"- **Financing Horizon**: {res['days_financed']} days\n"
                    f"- **Annualized Implied APR**: {res['implied_apr_percent']}%\n"
                    f"{savings_line}{borrow_cost_line}{net_benefit_line}"
                    f"- **Working Capital Recommendation Tier**: `{res['status']}`\n"
                    f"- **Strategic Recommendation**: {res['cfo_recommendation']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("TRADE_CREDIT"), prompt_type="concept", calculation="TRADE_CREDIT"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 8. Treasury Cash Drag & Idle Yield Loss
        if sub_intent == "CASH_DRAG":
            p_dict = extract_cash_drag_params(request.message, history=request.history)
            curr_bal = p_dict["current_balance"]
            burn = p_dict["monthly_burn"]
            yield_pct = p_dict["benchmark_annual_yield_pct"]
            reserve_mo = p_dict["target_reserve_months"]
            explicit_res = p_dict["explicit_reserve_target"]

            if (curr_bal is None or (burn is None and explicit_res is None)) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    if curr_bal is None:
                        curr_bal = Decimal(str(cash_res["current_balance"]))
                    if burn is None and explicit_res is None:
                        daily_burn = Decimal(str(cash_res["average_daily_burn"]))
                        burn = (daily_burn * Decimal("30.4167")).quantize(Decimal("0.01"))
                except Exception:
                    pass

            if curr_bal is not None and (burn is not None or explicit_res is not None):
                res = tool_calculate_cash_drag(
                    current_balance=curr_bal,
                    monthly_burn=burn,
                    benchmark_annual_yield_pct=yield_pct,
                    target_reserve_months=reserve_mo,
                    explicit_reserve_target=explicit_res,
                    currency=currency,
                )
                base_reply = (
                    f"### Treasury Cash Drag & Idle Liquidity Yield Audit\n\n"
                    f"- **Current Cash Balance**: {format_money(res['current_balance'], currency)}\n"
                    f"- **Target Operational Reserve**: {format_money(res['operational_reserve_target'], currency)}\n"
                    f"- **Idle Surplus Cash**: {format_money(res['idle_cash'], currency)}\n"
                    f"- **Benchmark Money Market APY**: {res['benchmark_annual_yield_pct']}%\n"
                    f"- **Annual Cash Drag / Yield Loss**: {format_money(res['annual_yield_loss'], currency)}/year ({format_money(res['monthly_yield_loss'], currency)}/month)\n"
                    f"- **Allocation Status**: `{res['allocation_status']}`\n"
                    f"- **Treasury Recommendation**: {res['recommendation']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("CASH_DRAG"), prompt_type="concept", calculation="CASH_DRAG"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 9. Free Cash Flow (FCFF & FCFE)
        if sub_intent == "FCFF":
            p_dict = extract_free_cash_flow_params(request.message, history=request.history)
            ocf = p_dict["operating_cash_flow"]
            capex = p_dict["capital_expenditures"]
            interest = p_dict["interest_expense"]
            tax_rate = p_dict["tax_rate_pct"]
            net_debt = p_dict["net_debt_issued"]

            if (ocf is None or capex is None) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    inflows = Decimal(str(cash_res.get("gross_inflows") or "0"))
                    outflows = Decimal(str(cash_res.get("gross_outflows") or "0"))
                    if ocf is None:
                        ocf = inflows - outflows
                    if capex is None:
                        capex = Decimal("0.00")
                except Exception:
                    pass

            if ocf is not None and capex is not None:
                res = tool_calculate_free_cash_flow(
                    operating_cash_flow=ocf,
                    capital_expenditures=capex,
                    interest_expense=interest,
                    tax_rate_pct=tax_rate,
                    net_debt_issued=net_debt,
                    currency=currency,
                )
                capex_val = res.get("capex") or res.get("capital_expenditures") or "0.00"
                fcff_val = res.get("fcff") or res.get("free_cash_flow_to_firm") or "0.00"
                fcfe_val = res.get("fcfe") or res.get("free_cash_flow_to_equity") or "0.00"
                status_val = res.get("cash_profile_status") or res.get("status") or ""
                rec_val = res.get("recommendation") or res.get("interpretation") or ""
                base_reply = (
                    f"### Free Cash Flow Audit (FCFF & FCFE)\n\n"
                    f"- **Operating Cash Flow (OCF)**: {format_money(res['operating_cash_flow'], currency)}\n"
                    f"- **Capital Expenditures (CapEx)**: {format_money(capex_val, currency)}\n"
                    f"- **Free Cash Flow to Firm (FCFF)**: **{format_money(fcff_val, currency)}**\n"
                    f"- **Free Cash Flow to Equity (FCFE)**: **{format_money(fcfe_val, currency)}**\n"
                    f"- **Cash Flow Quality Status**: `{status_val}`\n"
                    f"- **Working Capital Analysis**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("FCFF"), prompt_type="concept", calculation="FCFF"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 10. Multi-Currency Conversion
        if sub_intent == "CURRENCY_CONVERSION":
            p_dict = extract_currency_conversion_params(request.message, history=request.history)
            amt = p_dict["amount"]
            from_ccy = p_dict["from_currency"] or "USD"
            to_ccy = p_dict["to_currency"] or "EUR"
            ex_rate = p_dict["exchange_rate"]
            spread = p_dict["spread_bps"]

            if amt is not None:
                try:
                    res = tool_convert_currency(
                        amount=amt,
                        from_currency=from_ccy,
                        to_currency=to_ccy,
                        exchange_rate=ex_rate,
                        spread_bps=spread,
                    )
                except ValueError as exc:
                    # No live rate and no offline rate for this currency: ask for one instead of guessing.
                    return CopilotResponse(reply=str(exc), intent_detected="CASH_DIAGNOSTIC")
                base_reply = (
                    f"### Multi-Currency Conversion Audit\n\n"
                    f"- **Original Amount**: {res['from_symbol']}{format_amount(res['original_amount'])} ({res['from_currency_name']})\n"
                    f"- **Target Currency**: {res['to_symbol']} ({res['to_currency_name']} / `{res['to_currency']}`)\n"
                    f"- **Spot Exchange Rate**: `{res['spot_exchange_rate']}` ({res['exchange_rate_source']})\n"
                    f"- **Gross Converted**: {res['to_symbol']}{format_amount(res['gross_converted_amount'])}\n"
                    f"- **Bank Spread Fee ({format_amount(res['spread_bps'], 0)} bps)**: {res['to_symbol']}{format_amount(res['spread_fee'])}\n"
                    f"- **Net Converted Proceeds**: **{res['to_symbol']}{format_amount(res['net_converted_amount'])}**\n"
                    f"- **Effective Exchange Rate**: `{res['effective_exchange_rate']}`"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("CURRENCY_CONVERSION"), prompt_type="concept", calculation="CURRENCY_CONVERSION"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 11. Foreign Exchange (FX) Exposure & Value-at-Risk
        if sub_intent == "FX_EXPOSURE":
            p_dict = extract_fx_exposure_params(request.message, history=request.history)
            rec = p_dict["foreign_receivables"]
            pay = p_dict["foreign_payables"]
            base_ccy = p_dict["base_currency"] or "USD"
            foreign_ccy = p_dict["foreign_currency"] or "EUR"
            spot = p_dict["current_spot_rate"]
            shock = p_dict["adverse_shock_pct"]

            if rec is not None:
                try:
                    res = tool_calculate_fx_exposure(
                        foreign_receivables=rec,
                        foreign_payables=pay,
                        base_currency=base_ccy,
                        foreign_currency=foreign_ccy,
                        current_spot_rate=spot,
                        adverse_shock_pct=shock,
                    )
                except ValueError as exc:
                    # No live rate and no offline rate for this currency: ask for one instead of guessing.
                    return CopilotResponse(reply=str(exc), intent_detected="CASH_DIAGNOSTIC")
                hedge_note = "Forward contract hedge recommended." if res.get("recommend_forward_contract_hedge") else "Exposure within unhedged operating buffer."
                base_reply = (
                    f"### Foreign Exchange (FX) Exposure & VaR Audit\n\n"
                    f"- **Foreign Receivables**: {format_amount(res['foreign_receivables'])} {res['foreign_currency']}\n"
                    f"- **Foreign Payables**: {format_amount(res['foreign_payables'])} {res['foreign_currency']}\n"
                    f"- **Net Foreign Exposure (NOP)**: **{format_amount(res['net_foreign_exposure'])} {res['foreign_currency']}** ({res['base_equivalent_exposure']} {res['base_currency']} value)\n"
                    f"- **Position Posture**: `{res['position_type']}`\n"
                    f"- **Spot Rate**: `{res['current_spot_rate']}` ({res['rate_source']})\n"
                    f"- **Potential Volatility Loss ({format_amount(res['adverse_shock_pct'], 1)}% Shock)**: **{format_money(res['potential_cash_loss'], res['base_currency'])} {res['base_currency']}**\n"
                    f"- **Treasury Guidance**: {res['risk_summary']} {hedge_note}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("FX_EXPOSURE"), prompt_type="concept", calculation="FX_EXPOSURE"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # Bridge financing plan for the projected shortfall
        if sub_intent == "BRIDGE_PLAN":
            if not effective_csv:
                return CopilotResponse(
                    reply=get_missing_statement_guidance("diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )
            invoices_csv = None
            if request.session_id:
                from services.agent.session_store import session_store
                rec = session_store.get_or_create(request.session_id, tenant_id=request.tenant_id)
                invoices_csv = rec.invoices_csv if rec else None
            # Questions get the plan only; staging needs an explicit request (never stage from a question)
            # and a verified identity, since each staged leg writes into the tenant's ledger.
            stage = allow_staging and not is_question(request.message)
            res = tool_build_bridge_plan(effective_csv, invoices_csv=invoices_csv, stage=stage, tenant_id=request.tenant_id)
            if not res["has_shortfall"]:
                base_reply = f"### Bridge Financing Plan\n\n- **Projected Shortfall**: None within the forecast horizon\n- **Bridge Target**: {format_money(0, currency)}"
                return CopilotResponse(reply=enrich_fn(base_reply, prompt_type="diagnostic"), intent_detected="CASH_DIAGNOSTIC")

            leg_lines = "".join(
                f"- **Step {i}: {leg['source']}**: {format_money(leg['amount'], currency)} at {leg['apr_percent']}% APR "
                f"for {leg['term_days']} days (cost {format_money(leg['cost'], currency)})"
                f"{'' if leg['stageable'] else ', needs supplier agreement'}\n"
                for i, leg in enumerate(res["legs"], 1)
            )
            if res["staged"]:
                ids = ", ".join(s["intent_id"] for s in res["staged"])
                staged_line = f"- **Staged For Approval**: {len(res['staged'])} proposal(s) waiting for your review in Approvals ({ids})\n"
            elif not allow_staging:
                staged_line = (
                    "- **Staged For Approval**: None. Staging requires an authenticated tenant token "
                    "(`POST /api/v1/auth/token`), so this anonymous plan is advisory only.\n"
                )
            else:
                staged_line = "- **Staged For Approval**: None yet; ask me to prepare the plan to stage it\n"
            base_reply = (
                f"### Bridge Financing Plan\n\n"
                f"- **Projected Shortfall**: {format_money(res['shortfall'], currency)} on {res['deficit_date']}\n"
                f"- **Cash Buffer**: {format_money(res['buffer'], currency)}\n"
                f"- **Bridge Target**: {format_money(res['target'], currency)}\n"
                f"{leg_lines}"
                f"- **Total Estimated Cost**: {format_money(res['total_cost'], currency)}\n"
                f"- **Uncovered Gap**: {format_money(res['uncovered'], currency)}\n"
                f"{staged_line}"
            ).rstrip()
            staged_action = None
            if res["staged"]:
                # shortcut: CopilotResponse carries one proposal, so it shows the largest; all IDs are in the reply.
                top = max(res["staged"], key=lambda s: s["amount_cents"])
                staged_action = AgentActionProposal(
                    intent_id=top["intent_id"], action_type=top["action_type"], amount_cents=top["amount_cents"],
                    target_identifier=top["target_identifier"], status=top["status"],
                )
            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                intent_detected="CASH_DIAGNOSTIC",
                staged_action=staged_action,
            )

        # 12. What-if cash scenario rerun against the statement
        if sub_intent == "CASH_SCENARIO":
            if not effective_csv:
                return CopilotResponse(
                    reply=get_missing_statement_guidance("diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )
            p_dict = extract_cash_scenario_params(request.message, history=request.history)
            try:
                res = tool_run_cash_scenario(effective_csv, **p_dict)
            except (ValueError, TypeError):
                return CopilotResponse(
                    reply=enrich_fn(get_missing_param_guidance("CASH_SCENARIO"), prompt_type="concept", calculation="CASH_SCENARIO"),
                    intent_detected="CASH_DIAGNOSTIC",
                )

            def runway(days: Optional[int]) -> str:
                return f"{days} days" if days is not None else "Cash positive (no burn)"

            change = res["runway_change_days"]
            change_line = f"- **Runway Change**: {change:+d} days\n" if change is not None else ""
            delay_line = (
                f"- **Balance During Delay**: {format_money(res['balance_during_delay'], currency)}\n"
                if res["balance_during_delay"] is not None
                else ""
            )
            if res["scenario_has_deficit"] and res["scenario_days_until_deficit"] is not None:
                deficit = (
                    f"{format_money(res['scenario_shortfall'], currency)} shortfall on {res['scenario_deficit_date']} "
                    f"(day {res['scenario_days_until_deficit']}, `{res['scenario_severity']}`)"
                )
            else:
                deficit = "No projected deficit within the forecast horizon"
            base_reply = (
                f"### What-If Cash Scenario ({res['scenario'].replace('_', ' ').title()})\n\n"
                f"- **Current Balance**: {format_money(res['current_balance'], currency)}\n"
                f"- **Baseline Daily Burn**: {format_money(res['baseline_daily_burn'], currency)}/day\n"
                f"- **Scenario Daily Burn**: {format_money(res['scenario_daily_burn'], currency)}/day\n"
                f"- **Baseline Runway**: {runway(res['baseline_runway_days'])}\n"
                f"- **Scenario Runway**: {runway(res['scenario_runway_days'])}\n"
                f"{change_line}{delay_line}"
                f"- **Scenario Deficit**: {deficit}\n"
                f"- **Assumption**: {res['assumption']}"
            )
            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 13. Operational Outflow Category Breakdown
        if sub_intent == "OUTFLOW_BREAKDOWN":
            if not effective_csv:
                return CopilotResponse(
                    reply=get_missing_statement_guidance("diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )
            try:
                res = tool_analyze_outflow_breakdown(effective_csv)
            except Exception as e:
                return CopilotResponse(
                    reply=f"Unable to process statement for outflow breakdown: {str(e)}",
                    intent_detected="CASH_DIAGNOSTIC",
                )

            cats_lines = []
            for c in res["categories"]:
                cats_lines.append(
                    f"- **{c['category']}**: {format_money(c['total_amount'], currency)} ({c['percentage_of_outflows']}%, {c['transaction_count']} txs, avg: {format_money(c['average_transaction'], currency)})"
                )
            cats_formatted = "\n".join(cats_lines) if cats_lines else "- No outflows recorded in reviewed period."

            base_reply = (
                f"### Operational Outflow Breakdown by Category\n\n"
                f"- **Gross Outflows**: {format_money(res['gross_outflows'], currency)} across {res['period_days']} days\n"
                f"- **Average Daily Outflow**: {format_money(res['average_daily_outflow'], currency)}/day\n"
                f"- **Primary Cost Driver**: **{res['top_category']}** ({format_money(res['top_category_amount'], currency)}, {res['top_category_percentage']}% of outflows)\n\n"
                f"**Category Breakdown**:\n"
                f"{cats_formatted}"
            )
            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 14. Accounts Receivable Ageing & Collections Risk
        if sub_intent == "RECEIVABLES_AGEING":
            p_dict = extract_receivables_ageing_params(request.message, history=request.history)
            invoices_input = p_dict.get("invoices")
            as_of_date = p_dict.get("as_of_date")

            if not invoices_input and request.session_id:
                from services.agent.session_store import session_store
                rec = session_store.get_or_create(request.session_id, tenant_id=request.tenant_id)
                if rec and rec.invoices_csv:
                    invoices_input = rec.invoices_csv

            if not invoices_input:
                guidance = get_missing_param_guidance("RECEIVABLES_AGEING")
                return CopilotResponse(
                    reply=enrich_fn(guidance, prompt_type="concept", calculation="RECEIVABLES_AGEING"),
                    intent_detected="CASH_DIAGNOSTIC",
                )

            try:
                res = tool_analyze_receivables_ageing(invoices=invoices_input, as_of_date=as_of_date)
            except Exception as e:
                return CopilotResponse(
                    reply=f"Unable to process invoice data for receivables ageing: {str(e)}",
                    intent_detected="CASH_DIAGNOSTIC",
                )

            buckets = res["buckets"]
            bucket_lines = []
            for b_key in ("CURRENT", "1_30", "31_60", "61_90", "OVER_90"):
                b = buckets.get(b_key, {})
                bucket_lines.append(
                    f"- **{b.get('label', b_key)}**: {format_money(b.get('amount', 0), currency)} ({b.get('percentage', 0)}%, {b.get('invoice_count', 0)} invoices)"
                )
            buckets_formatted = "\n".join(bucket_lines)

            debtor_lines = []
            for d in res.get("top_debtors", []):
                debtor_lines.append(
                    f"- **{d['customer_name']}**: {format_money(d['total_open_balance'], currency)} open ({format_money(d['overdue_amount'], currency)} overdue, max {d['max_days_overdue']}d late, {d['share_of_total_ar']}% of AR)"
                )
            debtors_formatted = "\n".join(debtor_lines) if debtor_lines else "- No individual debtor concentration identified."

            actions_lines = [f"- {act}" for act in res.get("recommended_actions", [])]
            actions_formatted = "\n".join(actions_lines)

            base_reply = (
                f"### Accounts Receivable (AR) Ageing & Collections Audit\n\n"
                f"- **Snapshot Date**: {res['as_of_date']}\n"
                f"- **Total Outstanding AR**: {format_money(res['total_ar'], currency)}\n"
                f"- **Current (Not Overdue)**: {format_money(res['current_amount'], currency)}\n"
                f"- **Total Overdue**: {format_money(res['total_overdue'], currency)} ({res['overdue_ratio_pct']}% of AR)\n"
                f"- **Weighted Average Days Overdue**: {res['weighted_average_days_overdue']} days\n"
                f"- **Top Debtor Concentration**: {res['top_1_concentration_pct']}%\n"
                f"- **Receivables Risk Posture**: `{res['risk_tier']}`\n\n"
                f"**Ageing Schedule**:\n{buckets_formatted}\n\n"
                f"**Delinquent Customer Balances**:\n{debtors_formatted}\n\n"
                f"**Prescriptive Collection Actions**:\n{actions_formatted}"
            )
            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        # 15. Weekly Revenue Inflow Volatility & Predictability
        if sub_intent == "REVENUE_VOLATILITY":
            if not effective_csv:
                return CopilotResponse(
                    reply=get_missing_statement_guidance("diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )
            try:
                from services.ingestion.csv_parser import parse_bank_csv
                from services.matcher.liquidity_matcher import calculate_inflow_volatility

                from services.agent.tools import _normalize_statement_bytes

                content_bytes = _normalize_statement_bytes(effective_csv) if isinstance(effective_csv, str) else effective_csv
                ingest_res = parse_bank_csv(content_bytes)
                txs = ingest_res.accepted_rows
                cv, tier = calculate_inflow_volatility(txs)
                inflows = [t.amount for t in txs if t.amount > 0]
                total_inflows = sum(inflows, Decimal("0.00"))
                first_d = min(t.posted_on for t in txs)
                last_d = max(t.posted_on for t in txs)
                weeks = max(1, (last_d - first_d).days // 7)
                mean_weekly = total_inflows / Decimal(weeks)
                tier_desc = {
                    "LOW": "Stable, predictable recurring customer receipts (CV <= 0.35). Minimal cash volatility.",
                    "MODERATE": "Normal commercial fluctuations (0.35 < CV <= 0.75). Recommend standard 60-day buffer.",
                    "HIGH": "Lumpy, irregular revenue inflows (CV > 0.75). Elevated seasonal or project-based volatility.",
                }.get(tier, "Evaluated across weekly customer receipts.")
                base_reply = (
                    f"### Weekly Revenue Inflow Volatility & Cash Predictability Audit\n\n"
                    f"- **Weekly Revenue Inflow Volatility (CV)**: **{cv}**\n"
                    f"- **Inflow Volatility Tier**: `{tier}`\n"
                    f"- **Average Weekly Inflow**: ${float(mean_weekly):,.2f}\n"
                    f"- **Total Customer Receipts**: ${float(total_inflows):,.2f}\n"
                    f"- **Predictability Assessment**: {tier_desc}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                )
            except Exception as exc:
                return CopilotResponse(
                    reply=f"Revenue volatility could not be calculated: {str(exc)}",
                    intent_detected="CASH_DIAGNOSTIC",
                )

        return None

    @classmethod
    def handle_cash_flow_diagnosis(
        cls,
        request: AgentChatRequest,
        effective_csv: Optional[str],
        enrich_fn: Callable[[str, str], str],
    ) -> CopilotResponse:
        """Processes transactional bank statements into liquidity metrics and runway reserves."""
        if not effective_csv:
            return CopilotResponse(
                reply=get_missing_statement_guidance("diagnostic"),
                intent_detected="CASH_DIAGNOSTIC",
            )

        try:
            cash_result = tool_analyze_cash_flow(
                effective_csv,
                threshold_days=request.alert_threshold_days,
            )
            currency = cash_result["currency"]

            metrics = AgentMetricsSummary(
                current_balance=cash_result["current_balance"],
                net_period_change=cash_result["net_period_change"],
                average_daily_burn=cash_result["average_daily_burn"],
                runway_days=cash_result["runway_days"],
                cash_status=cash_result["cash_status"],
                gross_inflows=cash_result.get("gross_inflows"),
                gross_outflows=cash_result.get("gross_outflows"),
            )

            inflow_txt = f"- **Gross Inflows**: {format_money(metrics.gross_inflows, currency)}\n" if metrics.gross_inflows else ""
            outflow_txt = f"- **Gross Outflows**: {format_money(metrics.gross_outflows, currency)}\n" if metrics.gross_outflows else ""

            base_reply = (
                f"Financial diagnosis complete based on verified statement data:\n\n"
                f"- **Current Balance**: {format_money(metrics.current_balance, currency)}\n"
                f"{inflow_txt}{outflow_txt}"
                f"- **Average Daily Burn**: {format_money(metrics.average_daily_burn, currency)}/day\n"
                f"- **Runway Reserve**: {metrics.runway_days} days\n"
                f"- **Cash Posture Status**: `{metrics.cash_status}`\n\n"
                f"Your operations have approximately {metrics.runway_days} days of cash reserves remaining at the current net burn velocity."
            )

            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                intent_detected="CASH_DIAGNOSTIC",
                metrics=metrics,
            )
        except Exception as e:
            return CopilotResponse(
                reply=f"Unable to process statement for cash diagnosis: {str(e)}",
                intent_detected="CASH_DIAGNOSTIC",
            )
