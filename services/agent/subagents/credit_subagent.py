"""Credit and Debt Options Matcher Subagent.

Specializes in:
1. Debt Service Coverage Ratio (DSCR) & Fixed Charge Coverage Ratio (FCCR).
2. Commercial loan amortization scheduling & borrowing capacity.
3. Invoice factoring net proceeds & true APR calculation (predatory alert > 36%).
4. Consortium blockchain SHA-256 invoice hashing and double-financing validation.
5. WeBank inclusive finance digital underwriting dossiers.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from services.calculations.currency_registry import format_money
from services.agent.param_extractor import (
    extract_altman_z_params,
    extract_amortization_params,
    extract_dcf_params,
    extract_debt_capacity_params,
    extract_debt_service_burden_params,
    extract_debt_to_equity_params,
    extract_dscr_params,
    extract_enterprise_value_params,
    extract_factoring_params,
    extract_fccr_params,
    extract_interest_coverage_params,
    extract_invoice_hash_params,
    extract_lease_vs_buy_params,
    extract_net_debt_ebitda_params,
    extract_wacc_params,
)
from services.agent.schema import (
    AgentChatRequest,
    AgentMatchedOption,
    AgentMetricsSummary,
    CopilotResponse,
)
from services.agent.tools import (
    tool_annualized_statement_flows,
    tool_calculate_altman_z_score,
    tool_calculate_dcf_valuation,
    tool_calculate_debt_service_burden,
    tool_calculate_debt_to_equity,
    tool_calculate_dscr,
    tool_calculate_enterprise_value,
    tool_calculate_factoring_proceeds,
    tool_calculate_fccr,
    tool_calculate_interest_coverage,
    tool_calculate_lease_vs_buy,
    tool_calculate_loan_amortization,
    tool_calculate_net_debt_to_ebitda,
    tool_calculate_prudent_debt_capacity,
    tool_calculate_wacc,
    tool_underwrite_credit,
    tool_verify_invoice_hash,
)

from services.agent.session_store import session_store
from services.ingestion.csv_parser import CSVIngestionError
from services.agent.prompts import (
    get_missing_param_guidance,
    get_missing_statement_guidance,
    resolve_subagent_routing,
)


logger = logging.getLogger(__name__)

class CreditSubagent:
    """Specialist subagent for debt affordability, credit underwriting, and financing options."""

    @staticmethod
    def can_handle(sub_intent: Optional[str]) -> bool:
        if not sub_intent:
            return False
        return resolve_subagent_routing(sub_intent) == "CreditSubagent"


    @classmethod
    def handle_sub_intent(
        cls,
        sub_intent: str,
        request: AgentChatRequest,
        effective_csv: Optional[str],
        enrich_fn: Callable[[str, str], str],
        currency: str = "USD",
    ) -> Optional[CopilotResponse]:
        """Dispatches quantitative debt calculation requests to specialized tools."""
        # 1. Fixed Charge Coverage Ratio (FCCR)
        if sub_intent == "FCCR":
            p_dict = extract_fccr_params(request.message, history=request.history)
            eb = p_dict["ebitda"]
            fc = p_dict["fixed_charges"]
            ds = p_dict["total_debt_service"]

            eb_note = fc_note = ""
            if (eb is None or ds is None) and effective_csv:
                try:
                    flows = tool_annualized_statement_flows(effective_csv)
                    if eb is None:
                        eb, eb_note = flows["net"], flows["note"]
                    if fc is None:
                        fc = Decimal("0.00")
                        fc_note = " (assumed none; tell me your rent and lease payments)"
                except (ValueError, ArithmeticError):  # includes CSVIngestionError
                    pass

            if eb is not None and fc is not None and ds is not None:
                res = tool_calculate_fccr(ebitda=eb, fixed_charges=fc, total_debt_service=ds)
                rationale_txt = res.get("assessment") or res.get("rationale") or ""
                base_reply = (
                    f"### Fixed Charge Coverage Ratio (FCCR) Audit\n\n"
                    f"- **Annual EBITDA**: {format_money(res['ebitda'], currency)}{eb_note}\n"
                    f"- **Fixed Operational Charges**: {format_money(res['fixed_charges'], currency)}{fc_note}\n"
                    f"- **Total Annual Debt Service**: {format_money(res['total_debt_service'], currency)}\n"
                    f"- **FCCR Metric**: {res['fccr']}x\n"
                    f"- **Covenant Approval Tier**: `{res['underwriting_tier']}`\n"
                    f"- **Underwriting Assessment**: {rationale_txt}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("FCCR"), prompt_type="concept", calculation="FCCR"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 2. Maximum Prudent Debt Capacity
        if sub_intent == "DEBT_CAPACITY":
            p_dict = extract_debt_capacity_params(request.message, history=request.history)
            noi = p_dict["net_operating_income"]
            metrics = None

            est_note = ""
            if noi is None and effective_csv:
                try:
                    flows = tool_annualized_statement_flows(effective_csv)
                    noi = flows["net"]
                    est_note = flows["note"]
                except (ValueError, ArithmeticError):  # includes CSVIngestionError
                    pass

            if noi is not None and noi > Decimal("0.00"):
                res = tool_calculate_prudent_debt_capacity(
                    net_operating_income=noi,
                    target_dscr=p_dict["max_dscr"],
                    annual_interest_rate_pct=p_dict["annual_interest_rate_pct"],
                    term_years=2,
                )
                base_reply = (
                    f"### Prudent Debt Capacity & Borrowing Limit\n\n"
                    f"- **Net Operating Income (NOI)**: {format_money(res['net_operating_income'], currency)}{est_note}\n"
                    f"- **Target DSCR Covenant**: {res['target_dscr']}x\n"
                    f"- **Assumed Facility APR**: {res['annual_interest_rate_pct']}%\n"
                    f"- **Facility Term**: {res['term_years']} years\n"
                    f"- **Maximum Prudent Debt Capacity**: {format_money(res['maximum_prudent_debt_capacity'], currency)}\n"
                    f"- **Advisory Assessment**: {res['advisory_summary']}\n\n"
                    "Borrowing within this ceiling protects operating liquidity from debt over-leveraging."
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    metrics=metrics,
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("DEBT_CAPACITY"), prompt_type="concept", calculation="DEBT_CAPACITY"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 3. Debt Service Coverage Ratio (DSCR)
        if sub_intent == "DSCR":
            p_dict = extract_dscr_params(request.message, history=request.history)
            noi = p_dict["net_operating_income"]
            ads = p_dict.get("total_debt_service") or p_dict.get("annual_debt_service")

            est_note = ""
            if noi is None and effective_csv:
                try:
                    flows = tool_annualized_statement_flows(effective_csv)
                    noi = flows["net"]
                    est_note = flows["note"]
                except (ValueError, ArithmeticError):  # includes CSVIngestionError
                    pass

            if noi is not None and ads is not None:
                res = tool_calculate_dscr(net_operating_income=noi, total_debt_service=ads)
                debt_service_amt = res.get("total_debt_service") or res.get("annual_debt_service") or "0.00"
                analysis_txt = res.get("interpretation") or res.get("rationale") or ""
                base_reply = (
                    f"### Debt Service Coverage Ratio (DSCR) Assessment\n\n"
                    f"- **Net Operating Income (NOI)**: {format_money(res['net_operating_income'], currency)}{est_note}\n"
                    f"- **Annual Debt Service**: {format_money(debt_service_amt, currency)}\n"
                    f"- **DSCR Metric**: {res['dscr']}x\n"
                    f"- **Underwriting Status**: `{res['underwriting_status']}`\n"
                    f"- **Analysis**: {analysis_txt}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("DSCR"), prompt_type="concept", calculation="DSCR"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 4. Commercial Loan Amortization
        if sub_intent in ("AMORTIZATION", "LOAN_AMORTIZATION"):
            p_dict = extract_amortization_params(request.message, history=request.history)
            if p_dict.get("principal") and p_dict.get("annual_interest_rate_pct") and p_dict.get("term_months"):
                res = tool_calculate_loan_amortization(
                    principal=p_dict["principal"],
                    annual_interest_rate_pct=p_dict["annual_interest_rate_pct"],
                    term_months=p_dict["term_months"],
                    periods_elapsed=p_dict.get("periods_elapsed", 0),
                )
                total_paid = res.get("total_amount_paid") or res.get("total_payments") or "0.00"
                base_reply = (
                    f"### Commercial Loan Amortization Schedule\n\n"
                    f"- **Loan Principal**: {format_money(res['principal'], currency)}\n"
                    f"- **Annual Interest Rate**: {res['annual_interest_rate_pct']}%\n"
                    f"- **Loan Term**: {res['term_months']} months ({int(res['term_months']) // 12} years)\n"
                    f"- **Fixed Monthly Payment**: {format_money(res['monthly_payment'], currency)}/mo\n"
                    f"- **Total Interest Cost**: {format_money(res['total_interest'], currency)}\n"
                    f"- **Total Loan Obligation**: {format_money(total_paid, currency)}\n\n"
                    "To prepare this financing proposal for review, request action staging."
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )
            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("AMORTIZATION"), prompt_type="concept", calculation="AMORTIZATION"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 5. Invoice Factoring Net Proceeds & True APR
        if sub_intent == "FACTORING":
            p_dict = extract_factoring_params(request.message, history=request.history)
            if p_dict.get("invoice_amount") and p_dict.get("advance_rate_pct"):
                fee_given = p_dict.get("fee_rate_pct") is not None
                days_given = p_dict.get("collection_days") is not None
                res = tool_calculate_factoring_proceeds(
                    invoice_amount=p_dict["invoice_amount"],
                    advance_rate_pct=p_dict["advance_rate_pct"],
                    fee_rate_pct=p_dict["fee_rate_pct"] if fee_given else Decimal("3.00"),
                    collection_days=p_dict["collection_days"] if days_given else 45,
                )
                fee_note = "" if fee_given else " (assumed 3.00% fee; tell me your factor's rate)"
                days_note = "" if days_given else " (assumed; tell me your customer's payment terms)"
                pred_warning = (
                    "\n\n> [!WARNING]\n> **Predatory Rate Alert**: True annualized APR exceeds 36.00% benchmark. "
                    "Evaluate alternative credit lines or commercial factoring before proceeding."
                    if res["is_predatory"]
                    else "\n\n✅ Annualized APR complies with institutional non-predatory lending standards (<= 36.00%)."
                )
                base_reply = (
                    f"### Invoice Factoring Net Proceeds & True APR Analysis\n\n"
                    f"- **Invoice Face Value**: {format_money(res['invoice_face_value'], currency)}\n"
                    f"- **Advance Rate**: {res['advance_rate_percent']}% ({format_money(res['advance_amount'], currency)})\n"
                    f"- **Factoring Discount Fee**: {format_money(res['factoring_fee_amount'], currency)}{fee_note}\n"
                    f"- **Cash Received Now**: {format_money(res['advance_amount'], currency)}\n"
                    f"- **Total Net Proceeds After Collection**: {format_money(res['net_proceeds'], currency)}\n"
                    f"- **Collection Horizon**: {res['collection_days']} days{days_note}\n"
                    f"- **True Annualized APR**: {res['true_apr_percent']}%"
                    f"{pred_warning}\n\n"
                    "To prepare this invoice factoring proposal for review, request action staging."
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )
            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("FACTORING"), prompt_type="concept", calculation="FACTORING"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 6. Blockchain Invoice Hash Verification
        if sub_intent == "INVOICE_HASH":
            p_dict = extract_invoice_hash_params(request.message)
            if any(v is None for v in p_dict.values()):
                return CopilotResponse(
                    reply=enrich_fn(get_missing_param_guidance("INVOICE_HASH"), prompt_type="concept", calculation="INVOICE_HASH"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )
            res = tool_verify_invoice_hash(
                tax_id=p_dict["tax_id"],
                buyer_id=p_dict["buyer_id"],
                invoice_num=p_dict["invoice_num"],
                amount_cents=p_dict["amount_cents"],
            )
            risk_tag = (
                "⚠️ [DOUBLE-FINANCING ALERT: Invoice is already pledged to a consortium lender]"
                if res["is_double_financing_risk"]
                else "✅ [VALIDATED: Unencumbered asset available for financing]"
            )
            base_reply = (
                f"### Consortium Blockchain Invoice Hash Verification\n\n"
                f"- **Supplier Tax Identifier**: `{res['tax_id']}`\n"
                f"- **Buyer Account Identifier**: `{res['buyer_id']}`\n"
                f"- **Invoice Serial Number**: `{res['invoice_num']}`\n"
                f"- **Face Value**: {format_money(res['amount_dollars'], currency)}\n"
                f"- **Canonical Cryptographic Hash (SHA-256)**: `{res['invoice_hash']}`\n"
                f"- **Consortium Status**: `{res['consortium_status']}`\n"
                f"- **Registry Audit**: {risk_tag}\n\n"
                "This cryptographic verification ensures invoice uniqueness across consortium lenders on FISCO BCOS."
            )
            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="underwriting"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 7. Debt-to-Equity (D/E) Ratio
        if sub_intent == "DEBT_TO_EQUITY":
            p_dict = extract_debt_to_equity_params(request.message, history=request.history)
            debt = p_dict["total_debt"]
            equity = p_dict["total_equity"]

            if debt is not None and equity is not None:
                res = tool_calculate_debt_to_equity(total_debt=debt, total_equity=equity)
                base_reply = (
                    f"### Debt-to-Equity (D/E) Leverage Audit\n\n"
                    f"- **Total Debt Obligations**: {format_money(res['total_debt'], currency)}\n"
                    f"- **Total Shareholder Equity**: {format_money(res['total_equity'], currency)}\n"
                    f"- **Debt-to-Equity Ratio**: {res['debt_to_equity_ratio']}x\n"
                    f"- **Leverage Profile**: `{res['leverage_tier']}`\n"
                    f"- **Covenant Assessment**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("DEBT_TO_EQUITY"), prompt_type="concept", calculation="DEBT_TO_EQUITY"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 8. Interest Coverage Ratio (Times Interest Earned - TIE)
        if sub_intent == "INTEREST_COVERAGE":
            p_dict = extract_interest_coverage_params(request.message, history=request.history)
            ebit = p_dict["ebit"]
            interest = p_dict["interest_expense"]

            est_note = ""
            if ebit is None and effective_csv:
                try:
                    flows = tool_annualized_statement_flows(effective_csv)
                    ebit = flows["net"]
                    est_note = flows["note"]
                except (ValueError, ArithmeticError):  # includes CSVIngestionError
                    pass

            if ebit is not None and interest is not None:
                res = tool_calculate_interest_coverage(ebit=ebit, interest_expense=interest)
                base_reply = (
                    f"### Interest Coverage Ratio (TIE) Audit\n\n"
                    f"- **Operating Income (EBIT)**: {format_money(res['ebit'], currency)}{est_note}\n"
                    f"- **Annual Interest Expense**: {format_money(res['interest_expense'], currency)}\n"
                    f"- **Interest Coverage Ratio**: {res['interest_coverage_ratio']}x\n"
                    f"- **Covenant Health Tier**: `{res['covenant_tier']}`\n"
                    f"- **Debt Service Assessment**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("INTEREST_COVERAGE"), prompt_type="concept", calculation="INTEREST_COVERAGE"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 9. Commercial Equipment Lease vs Buy NPV Analysis
        if sub_intent == "LEASE_VS_BUY":
            p_dict = extract_lease_vs_buy_params(request.message, history=request.history)
            price = p_dict["purchase_price"]
            lease_pay = p_dict["annual_lease_payment"]
            term = p_dict["term_years"]
            disc_rate = p_dict["discount_rate_pct"]
            tax_rate = p_dict["corporate_tax_rate_pct"]
            salvage = p_dict["estimated_salvage_value"]
            maint = p_dict["annual_maintenance_if_bought"]

            if price is not None and lease_pay is not None and term is not None and disc_rate is not None:
                res = tool_calculate_lease_vs_buy(
                    purchase_price=price,
                    annual_lease_payment=lease_pay,
                    term_years=term,
                    discount_rate_pct=disc_rate,
                    corporate_tax_rate_pct=tax_rate,
                    estimated_salvage_value=salvage,
                    annual_maintenance_if_bought=maint,
                )
                base_reply = (
                    f"### Equipment Lease vs. Buy Net Present Value (NPV) Analysis\n\n"
                    f"- **Equipment Purchase Price**: {format_money(res['purchase_price'], currency)}\n"
                    f"- **Annual Lease Payment**: {format_money(res['annual_lease_payment'], currency)}/yr ({res['term_years']} years)\n"
                    f"- **Discount Rate / Cost of Capital**: {res['discount_rate_pct']}%\n"
                    f"- **Present Value Cost (Leasing)**: {format_money(res['pv_leasing_cost'], currency)}\n"
                    f"- **Present Value Cost (Buying)**: {format_money(res['pv_buying_cost'], currency)}\n"
                    f"- **Net Financial Advantage**: {format_money(res['savings_dollars'], currency)} favoring `{res['recommended_action']}`\n"
                    f"- **Decision Policy**: `{res['status']}`\n"
                    f"- **Capital Allocation Guidance**: {res['recommendation']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("LEASE_VS_BUY"), prompt_type="concept", calculation="LEASE_VS_BUY"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 11. Altman Z'-Score for Private SME Insolvency Distress
        if sub_intent == "ALTMAN_Z_SCORE":
            p_dict = extract_altman_z_params(request.message, history=request.history)
            wc = p_dict["working_capital"]
            re_val = p_dict["retained_earnings"]
            ebit = p_dict["ebit"]
            eq = p_dict["book_value_equity"]
            liab = p_dict["total_liabilities"]
            assets = p_dict["total_assets"]
            rev = p_dict["revenue"]

            if all(v is not None for v in (wc, re_val, ebit, eq, liab, assets, rev)):
                res = tool_calculate_altman_z_score(
                    working_capital=wc,
                    retained_earnings=re_val,
                    ebit=ebit,
                    book_value_equity=eq,
                    total_liabilities=liab,
                    total_assets=assets,
                    revenue=rev,
                )
                z_score_val = res.get("altman_z_score") or res.get("z_score") or "0.00"
                zone_val = res.get("distress_zone") or res.get("zone") or "UNKNOWN"
                class_val = res.get("distress_level") or res.get("classification") or ""
                rec_val = res.get("recommendation") or res.get("interpretation") or ""
                base_reply = (
                    f"### Altman Z'-Score SME Insolvency Distress Audit\n\n"
                    f"- **Working Capital**: {format_money(res['working_capital'], currency)}\n"
                    f"- **Retained Earnings**: {format_money(res['retained_earnings'], currency)}\n"
                    f"- **Operating Income (EBIT)**: {format_money(res['ebit'], currency)}\n"
                    f"- **Book Value of Equity**: {format_money(res['book_value_equity'], currency)}\n"
                    f"- **Total Liabilities**: {format_money(res['total_liabilities'], currency)}\n"
                    f"- **Total Balance Sheet Assets**: {format_money(res['total_assets'], currency)}\n"
                    f"- **Annual Commercial Revenue**: {format_money(res['revenue'], currency)}\n"
                    f"- **Altman Z'-Score**: **{z_score_val}**\n"
                    f"- **Credit Distress Tier**: `{zone_val}`\n"
                    f"- **Credit Risk Classification**: {class_val}\n"
                    f"- **Underwriting Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("ALTMAN_Z_SCORE"), prompt_type="concept", calculation="ALTMAN_Z_SCORE"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 12. Net Debt to EBITDA Leverage Ratio
        if sub_intent == "NET_DEBT_TO_EBITDA":
            p_dict = extract_net_debt_ebitda_params(request.message, history=request.history)
            debt = p_dict["total_debt"]
            cash = p_dict["cash_and_equivalents"]
            ebitda = p_dict["ebitda"]

            if debt is not None and ebitda is not None:
                res = tool_calculate_net_debt_to_ebitda(
                    total_debt=debt,
                    cash_and_equivalents=cash if cash is not None else Decimal("0.00"),
                    ebitda=ebitda,
                )
                ratio_val = res.get("net_debt_to_ebitda_ratio") or res.get("net_debt_to_ebitda") or "0.00"
                tier_val = res.get("leverage_tier") or res.get("tier") or "UNKNOWN"
                status_val = res.get("policy_status") or res.get("status") or ""
                rec_val = res.get("recommendation") or res.get("assessment") or ""
                base_reply = (
                    f"### Net Debt to EBITDA Leverage Audit\n\n"
                    f"- **Total Debt Obligations**: {format_money(res['total_debt'], currency)}\n"
                    f"- **Cash & Equivalents**: {format_money(res['cash_and_equivalents'], currency)}\n"
                    f"- **Net Debt**: {format_money(res['net_debt'], currency)}\n"
                    f"- **Annual Operating EBITDA**: {format_money(res['ebitda'], currency)}\n"
                    f"- **Net Debt to EBITDA Multiple**: **{ratio_val}x**\n"
                    f"- **Institutional Leverage Tier**: `{tier_val}`\n"
                    f"- **Credit Covenant Status**: `{status_val}`\n"
                    f"- **Underwriting Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("NET_DEBT_TO_EBITDA"), prompt_type="concept", calculation="NET_DEBT_TO_EBITDA"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 13. Debt Service Burden Ratio
        if sub_intent == "DEBT_SERVICE_BURDEN":
            p_dict = extract_debt_service_burden_params(request.message, history=request.history)
            svc = p_dict["annual_debt_service"]
            rev = p_dict["gross_revenue"]

            est_note = ""
            if rev is None and effective_csv:
                try:
                    flows = tool_annualized_statement_flows(effective_csv)
                    rev = flows["inflows"]
                    est_note = flows["note"]
                except (ValueError, ArithmeticError):  # includes CSVIngestionError
                    pass

            if svc is not None and rev is not None:
                res = tool_calculate_debt_service_burden(
                    annual_debt_service=svc,
                    gross_revenue=rev,
                )
                rev_val = res.get("annual_revenue") or res.get("gross_revenue") or "0.00"
                burden_val = res.get("debt_service_burden_pct") or "0.00"
                tier_val = res.get("burden_tier") or res.get("tier") or "UNKNOWN"
                status_val = res.get("policy_status") or res.get("status") or ""
                rec_val = res.get("recommendation") or res.get("assessment") or ""
                base_reply = (
                    f"### Debt Service Burden Audit\n\n"
                    f"- **Annual Debt Service Obligations**: {format_money(res['annual_debt_service'], currency)}\n"
                    f"- **Gross Commercial Revenue**: {format_money(rev_val, currency)}{est_note}\n"
                    f"- **Debt Service Burden**: **{burden_val}%** of revenue\n"
                    f"- **Debt Service Tier**: `{tier_val}`\n"
                    f"- **Credit Covenant Status**: `{status_val}`\n"
                    f"- **Underwriting Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("DEBT_SERVICE_BURDEN"), prompt_type="concept", calculation="DEBT_SERVICE_BURDEN"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 14. Weighted Average Cost of Capital (WACC)
        if sub_intent == "WACC":
            p_dict = extract_wacc_params(request.message, history=request.history)
            eq = p_dict["equity_value"]
            debt = p_dict["total_debt"]
            ke = p_dict["cost_of_equity_pct"]
            kd = p_dict["pre_tax_cost_of_debt_pct"]
            tax_rate = p_dict["corporate_tax_rate_pct"]

            if eq is not None and debt is not None and ke is not None and kd is not None:
                res = tool_calculate_wacc(
                    equity_value=eq,
                    total_debt=debt,
                    cost_of_equity_pct=ke,
                    pre_tax_cost_of_debt_pct=kd,
                    corporate_tax_rate_pct=tax_rate,
                )
                cap_base = res.get("total_firm_capital") or res.get("total_firm_value") or "0.00"
                rec_val = res.get("recommendation") or res.get("interpretation") or ""
                base_reply = (
                    f"### Weighted Average Cost of Capital (WACC) Analysis\n\n"
                    f"- **Equity Capital Value**: {format_money(res['equity_value'], currency)} ({res['equity_weight_pct']}%)\n"
                    f"- **Total Debt Obligations**: {format_money(res['total_debt'], currency)} ({res['debt_weight_pct']}%)\n"
                    f"- **Cost of Equity (Ke)**: {res['cost_of_equity_pct']}%\n"
                    f"- **Pre-Tax Cost of Debt (Kd)**: {res['pre_tax_cost_of_debt_pct']}%\n"
                    f"- **Corporate Tax Shield**: {tax_rate}% (Effective After-Tax Kd: {res['after_tax_cost_of_debt_pct']}%)\n"
                    f"- **Total Enterprise Capital Base**: {format_money(cap_base, currency)}\n"
                    f"- **Weighted Average Cost of Capital (WACC)**: **{res['wacc_pct']}%**\n"
                    f"- **Hurdle Rate Guidance**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("WACC"), prompt_type="concept", calculation="WACC"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 15. Enterprise Value & Valuation Multiples
        if sub_intent == "ENTERPRISE_VALUE":
            p_dict = extract_enterprise_value_params(request.message, history=request.history)
            eq = p_dict["equity_value"]
            debt = p_dict["total_debt"]
            cash = p_dict["cash_and_equivalents"]
            ebitda = p_dict["ebitda"]
            rev = p_dict["revenue"]

            if eq is not None and debt is not None:
                res = tool_calculate_enterprise_value(
                    equity_value=eq,
                    total_debt=debt,
                    cash_and_equivalents=cash,
                    ebitda=ebitda,
                    revenue=rev,
                )
                multiples_lines = ""
                if res.get("ev_to_ebitda") and res.get("ev_to_ebitda") != "N/A":
                    multiples_lines += f"- **EV / EBITDA Multiple**: **{res['ev_to_ebitda']}x**\n"
                if res.get("ev_to_revenue") and res.get("ev_to_revenue") != "N/A":
                    multiples_lines += f"- **EV / Revenue Multiple**: **{res['ev_to_revenue']}x**\n"

                rec_val = res.get("recommendation") or res.get("assessment") or ""
                base_reply = (
                    f"### Enterprise Value & Valuation Multiples Audit\n\n"
                    f"- **Equity Value (Market Cap)**: {format_money(res['equity_value'], currency)}\n"
                    f"- **Total Debt Obligations**: {format_money(res['total_debt'], currency)}\n"
                    f"- **Cash & Liquid Equivalents**: {format_money(res['cash_and_equivalents'], currency)}\n"
                    f"- **Net Debt**: {format_money(res['net_debt'], currency)}\n"
                    f"- **Enterprise Value (EV)**: **{format_money(res['enterprise_value'], currency)}**\n"
                    f"{multiples_lines}"
                    f"- **Valuation Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("ENTERPRISE_VALUE"), prompt_type="concept", calculation="ENTERPRISE_VALUE"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 16. Discounted Cash Flow (DCF) Valuation
        if sub_intent == "DCF_VALUATION":
            p_dict = extract_dcf_params(request.message, history=request.history)
            flows = p_dict["projected_cash_flows"]
            wacc = p_dict["wacc_discount_rate_pct"]
            g_rate = p_dict["perpetual_growth_rate_pct"]

            if flows and wacc is not None:
                res = tool_calculate_dcf_valuation(
                    projected_cash_flows=flows,
                    wacc_discount_rate_pct=wacc,
                    perpetual_growth_rate_pct=g_rate,
                )
                flows_str = ", ".join(f"{format_money(f, currency, 0)}" for f in flows)
                wacc_val = res.get("wacc_pct") or res.get("wacc_discount_rate_pct")
                g_val = res.get("terminal_growth_rate_pct") or res.get("perpetual_growth_rate_pct")
                years_val = res.get("forecast_years") or res.get("projection_years") or len(flows)
                ev = Decimal(str(res['enterprise_value']))
                pv_tv = Decimal(str(res['pv_terminal_value']))
                tv_share = f"{(pv_tv / ev * 100):.1f}" if ev > 0 else "0.0"
                rec_val = res.get("recommendation") or ""

                base_reply = (
                    f"### Discounted Cash Flow (DCF) Enterprise Valuation\n\n"
                    f"- **Projected Cash Flows**: {flows_str}\n"
                    f"- **WACC Discount Rate**: {wacc_val}%\n"
                    f"- **Perpetual Terminal Growth Rate**: {g_val}%\n"
                    f"- **Present Value of Explicit Cash Flows**: {format_money(res['pv_explicit_cash_flows'], currency)}\n"
                    f"- **Terminal Value (Year {years_val})**: {format_money(res['terminal_value'], currency)}\n"
                    f"- **Present Value of Terminal Value**: {format_money(pv_tv, currency)}\n"
                    f"- **Enterprise Value (DCF)**: **{format_money(ev, currency)}**\n"
                    f"- **Terminal Value Contribution**: {tv_share}% of Enterprise Value\n"
                    f"- **Advisory Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("DCF_VALUATION"), prompt_type="concept", calculation="DCF_VALUATION"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        return None

    @classmethod
    def handle_underwriting_evaluation(
        cls,
        request: AgentChatRequest,
        effective_csv: Optional[str],
        enrich_fn: Callable[[str, str], str],
        session_id: Optional[str] = None,
        tenant_id: str = "SME-DEFAULT",
    ) -> CopilotResponse:
        """Runs full digital underwriting dossier generation and financing options matching."""
        if not effective_csv:
            return CopilotResponse(
                reply=get_missing_statement_guidance("underwriting"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        try:
            uw_result = tool_underwrite_credit(effective_csv, nsf_count=request.nsf_count)
            currency = uw_result["dossier"]["currency"]
            if session_id:
                session_store.update_statement(
                    session_id,
                    effective_csv,
                    dossier=uw_result.get("dossier"),
                    tenant_id=tenant_id,
                )

            dossier = uw_result["dossier"]
            matched_opts = [AgentMatchedOption(**opt) for opt in uw_result["matched_options"]]

            metrics = AgentMetricsSummary(
                daily_average_balance=dossier["daily_average_balance"],
                risk_tier=dossier["risk_tier"],
                max_qualified_limit=dossier["max_qualified_limit"],
                revenue_volatility_cv=dossier.get("revenue_volatility_cv"),
                volatility_tier=dossier.get("volatility_tier"),
            )

            top_option = matched_opts[0] if matched_opts else None
            opt_summary = (
                f"Top matched facility is {top_option.facility_name} from {top_option.provider} "
                f"at {top_option.apr_percent}% APR (Max: {format_money(top_option.max_amount, currency)})."
                if top_option
                else "No non-predatory credit facilities currently meet the underwriting criteria."
            )

            reply = (
                f"### Credit Underwriting Assessment\n\n"
                f"- **Underwriting evaluation complete**. Classification: `{dossier['risk_tier']}`\n"
                f"- **Daily Average Balance (DAB)**: {format_money(dossier['daily_average_balance'], currency)}\n"
                f"- **Maximum Qualified Limit**: {format_money(dossier['max_qualified_limit'], currency)}\n"
                f"- **Matched Facility**: {opt_summary}\n\n"
                "To apply, request staging for the chosen facility."
            )
        except CSVIngestionError as exc:
            return CopilotResponse(
                reply=f"Statement ingestion failed: {exc.code} - {exc}",
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )
        except Exception:
            # Internal failure: log the trace, never echo exception text to the owner.
            logger.exception("Underwriting failed")
            return CopilotResponse(
                reply="Underwriting could not be completed for this statement. Please check the file and try again.",
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        return CopilotResponse(
            reply=enrich_fn(reply, prompt_type="underwriting"),
            intent_detected="CREDIT_UNDERWRITING",
            metrics=metrics,
            matched_options=matched_opts,
            requires_biometric_hitl=False,
        )
