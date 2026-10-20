"""Fine-tune dataset generator for the SME Finance Copilot CashPilot-2B LoRA adapters.

Every example is shaped exactly like a runtime call to the local model
(LocalTransformersEngine.generate never passes tools):

    system    = the production prompt from services/agent/prompts.py, rendered with the
                same deterministic engine output (base_reply) the supervisor builds
    user      = the owner's question, kept only if the production router sends it down
                the branch that produced base_reply
    assistant = 3-6 sentences of plain prose that answer first, copy figures verbatim from
                base_reply, explain the impact and end with one action

Rows are dropped unless the reply passes numbers_are_grounded() (the runtime guard) and
survives sanitize_cfo_reply() unchanged, so the model never learns text the code deletes.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

# Disables LLM routing and on-disk model checks inside the services imported below.
os.environ.setdefault("PYTEST_CURRENT_TEST", "generate_finetune_dataset")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.agent.dynamic_router import classify_intent_dynamic, classify_sub_intent_dynamic
from services.agent.knowledge import append_reference_cards, format_reference_cards, load_cards, retrieve_cards
from services.agent.prompts import (
    evaluate_persona_policy,
    get_cash_diagnostic_prompt,
    get_concept_prompt,
    get_conversational_system_prompt,
    get_credit_underwriting_prompt,
    get_missing_statement_prompt,
    numbers_are_grounded,
    sanitize_cfo_reply,
)
from services.agent.schema import AgentChatRequest
from services.agent.subagents import CreditSubagent, LiquiditySubagent, RiskManagerSubagent
from services.agent.supervisor import is_off_topic_query
from services.agent.tools import (
    tool_analyze_cash_flow,
    tool_analyze_outflow_breakdown,
    tool_analyze_receivables_ageing,
    tool_calculate_break_even,
    tool_calculate_trade_credit_apr,
    tool_underwrite_credit,
)

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../dataset"))
SUBAGENTS = (CreditSubagent, LiquiditySubagent, RiskManagerSubagent)
CASH_BRANCHES = ("RUNWAY", "BALANCE", "BURN", "ADVICE", "DEFICIT")

EVAL_SET_PATH = os.path.join(OUTPUT_DIR, "eval_set.jsonl")
EVAL_QUESTIONS: set[str] = set()
if os.path.exists(EVAL_SET_PATH):
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as _ef:
        for _line in _ef:
            if _line.strip():
                _case = json.loads(_line)
                for _m in reversed(_case.get("messages", [])):
                    if _m.get("role") == "user":
                        EVAL_QUESTIONS.add(_m.get("content", "").strip().lower())
                        break

from services.agent.local_transformers import BASE_MODEL_ID, base_on_disk
TOKENIZER_DIR = base_on_disk(BASE_MODEL_ID) or BASE_MODEL_ID
_TOKENIZER = None
# A base that is not on disk fetches only its small tokenizer files, never the weights.
try:
    from transformers import AutoTokenizer
    _TOKENIZER = AutoTokenizer.from_pretrained(TOKENIZER_DIR, trust_remote_code=True)
except Exception as _tok_err:
    print(f"Warning: could not load tokenizer: {_tok_err}")


def compute_ngram_overlap(text: str, source: str, n: int = 4) -> float:
    """Computes the fraction of n-grams in text that occur verbatim in source."""
    words_t = re.findall(r"\b\w+\b", text.lower())
    words_s = set()
    s_tokens = re.findall(r"\b\w+\b", source.lower())
    if len(s_tokens) < n or len(words_t) < n:
        return 0.0

    for i in range(len(s_tokens) - n + 1):
        words_s.add(tuple(s_tokens[i : i + n]))

    overlap_count = 0
    total_ngrams = len(words_t) - n + 1
    for i in range(total_ngrams):
        if tuple(words_t[i : i + n]) in words_s:
            overlap_count += 1
    return overlap_count / total_ngrams if total_ngrams > 0 else 0.0


# Copied from supervisor.py: the general-chat path appends one of these to the CONVERSATIONAL prompt.
STATEMENT_LOADED_NOTE = "\nNote: A transactional bank statement is already loaded into session."
NO_STATEMENT_DIRECTIVE = (
    "\nCRITICAL SAFETY DIRECTIVE: No bank statement CSV has been loaded yet. "
    "You MUST NOT invent, guess, or output any financial figures, dollar amounts, "
    "deficit amounts, burn rates, or metric bullet lists. "
    "Introduce yourself directly in one or two sentences as the Autonomous SME Finance Copilot "
    "and ask the business owner to upload their bank statement CSV."
)


def money(value: Any) -> str:
    """Matches the supervisor's f"${float(v):,.2f}" output without float currency math."""
    return f"${Decimal(str(value)):,.2f}"


def plain(value: Any) -> str:
    return f"{Decimal(str(value)):,.2f}"


def pick(rng: random.Random, options: List[str], **fields: Any) -> str:
    return rng.choice(options).format(**fields)


# ==============================================================================
# Runtime routing (production router, cached per question)
# ==============================================================================

_ROUTE_CACHE: Dict[tuple, tuple] = {}


def route(question: str, has_csv: bool) -> tuple:
    """Returns (intent, sub_intent, handled_by_quant_subagent) as the supervisor would see them."""
    key = (question, has_csv)
    if key not in _ROUTE_CACHE:
        if is_off_topic_query(question):
            _ROUTE_CACHE[key] = ("OFF_TOPIC", None, False)
        else:
            intent = classify_intent_dynamic(message=question, history=None, has_csv=has_csv)
            sub = classify_sub_intent_dynamic(question)
            _ROUTE_CACHE[key] = (intent, sub, any(s.can_handle(sub) for s in SUBAGENTS))
    return _ROUTE_CACHE[key]


def cash_branch(question: str) -> Optional[str]:
    intent, sub, quant = route(question, True)
    if intent != "CASH_DIAGNOSTIC" or quant:
        return None
    return sub if sub in CASH_BRANCHES else "SUMMARY"


# ==============================================================================
# Synthetic bank statements
# ==============================================================================

PROFILES = {
    # name: (opening balance range, daily inflow mean, daily outflow mean)
    "cash_positive": ((40_000, 250_000), (2_500, 9_000), (600, 2_500)),
    "slow_burn": ((60_000, 300_000), (1_000, 4_000), (1_800, 6_000)),
    "fast_burn": ((15_000, 90_000), (300, 1_500), (1_500, 5_000)),
    "near_deficit": ((8_000, 40_000), (400, 1_500), (1_200, 3_500)),
    "overdrawn": ((1_000, 6_000), (200, 800), (900, 2_500)),
}
PROFILE_WEIGHTS = [3, 4, 3, 3, 1]
INFLOW_LABELS = ["Client Invoice Payment", "Customer Transfer", "Stripe Payout", "Wholesale Order Receipt", "POS Settlement", "Retainer Payment"]
OUTFLOW_LABELS = ["Supplier Payment", "Payroll Run", "Inventory Purchase", "Utilities", "Software Subscriptions", "Contractor Invoice", "Fuel and Logistics"]


def make_statement(rng: random.Random, profile: str, days: Optional[int] = None) -> str:
    (bal_lo, bal_hi), (in_lo, in_hi), (out_lo, out_hi) = PROFILES[profile]
    balance = Decimal(rng.randrange(bal_lo, bal_hi, 50))
    inflow_mu, outflow_mu = rng.randint(in_lo, in_hi), rng.randint(out_lo, out_hi)
    rent = Decimal(rng.randrange(1_500, 9_000, 250))
    loan = Decimal(rng.randrange(800, 4_000, 100)) if rng.random() < 0.4 else None
    start = date(2026, rng.randint(3, 8), 1)
    if days is None:
        days = rng.choice([30, 45, 60, 75, 90])
    rows = ["transaction_id,posted_on,amount,currency,description,closing_balance"]
    tx = 0
    for offset in range(days):
        day = start + timedelta(days=offset)
        entries = []
        if day.day == 1:
            entries.append((-rent, "Office Rent"))
        if loan is not None and day.day == 15:
            entries.append((-loan, "Term Loan Repayment"))
        if rng.random() < 0.35:
            entries.append((Decimal(rng.randint(inflow_mu // 2, inflow_mu * 2)), rng.choice(INFLOW_LABELS)))
        if rng.random() < 0.65:
            entries.append((-Decimal(rng.randint(outflow_mu // 2, outflow_mu * 3 // 2)), rng.choice(OUTFLOW_LABELS)))
        for amount, label in entries:
            tx += 1
            balance += amount
            rows.append(f"tx_{tx:04d},{day.isoformat()},{amount:.2f},USD,{label},{balance:.2f}")
    return "\n".join(rows) + "\n"


# ==============================================================================
# base_reply builders (mirror supervisor.run_copilot_supervisor branches exactly)
# ==============================================================================


def runway_desc(cash: Dict[str, Any]) -> str:
    return f"{cash['runway_days']} days" if cash["runway_days"] is not None else "Infinite (Cash positive)"


def cash_base_reply(cash: Dict[str, Any], branch: str) -> str:
    rd = runway_desc(cash)
    pred = f" {cash['predictive_explanation']}" if cash.get("predictive_explanation") else ""
    target = ""
    if cash.get("target_horizon_days") and cash.get("forecast_target_balance") is not None:
        tier_label = f" [{cash.get('confidence_tier', 'HIGH')} CONFIDENCE]"
        advisory = f" {cash['advisory_note']}" if cash.get("advisory_note") else ""
        target = (
            f" Specifically for Day {cash['target_horizon_days']} ({cash['target_horizon_date']}){tier_label}, "
            f"projected balance is {money(cash['forecast_target_balance'])}.{advisory}"
        )
    tail = f"{pred}{target}"

    if branch == "RUNWAY":
        return f"You have {rd} of cash runway remaining at an average daily burn of {money(cash['average_daily_burn'])}/day (current balance: {money(cash['current_balance'])}, Status: {cash['cash_status']}).{tail}"
    if branch == "BALANCE":
        return f"Your current cash balance is {money(cash['current_balance'])} {cash['currency']} (net change across reviewed period: {money(cash['net_period_change'])}).{tail}"
    if branch == "BURN":
        return f"Your average daily burn rate is {money(cash['average_daily_burn'])}/day (gross outflows: {money(cash['gross_outflows'])} vs inflows: {money(cash['gross_inflows'])}), providing {rd} of cash runway remaining (Status: {cash['cash_status']}).{tail}"
    if branch == "ADVICE":
        if cash.get("has_projected_deficit"):
            shortfall = cash.get("projected_shortfall_amount")
            bridge = cash.get("recommended_bridge_amount") or shortfall
            tmpl = evaluate_persona_policy(prompt_type="ADVICE_DEFICIT").get("guidance_text", "")
            head = tmpl.format(
                cash_status=cash["cash_status"], runway_desc=rd,
                shortfall=cash.get("projected_shortfall_amount", "0.00"),
                date=cash.get("projected_deficit_date", "upcoming dates"),
                trigger=cash.get("primary_deficit_trigger", "recurring commitments"),
                bridge=money(bridge) if bridge else "liquidity support",
            )
        elif cash.get("cash_status") == "WATCH":
            tmpl = evaluate_persona_policy(prompt_type="ADVICE_WATCH").get("guidance_text", "")
            head = tmpl.format(
                cash_status="WATCH", runway_desc=rd, balance=plain(cash["current_balance"]),
                burn=plain(cash["average_daily_burn"]), runway_days=cash["runway_days"],
            )
        else:
            tmpl = evaluate_persona_policy(prompt_type="ADVICE_HEALTHY").get("guidance_text", "")
            head = tmpl.format(cash_status="HEALTHY", runway_desc=rd, balance=plain(cash["current_balance"]))
        return f"{head}{tail}"
    if branch == "DEFICIT":
        if cash.get("has_projected_deficit"):
            tmpl = evaluate_persona_policy(prompt_type="DEFICIT_EARLY_WARNING").get("guidance_text", "")
            head = tmpl.format(
                shortfall=cash.get("projected_shortfall_amount", "0.00"), days=cash.get("days_until_deficit", "N/A"),
                date=cash.get("projected_deficit_date", "N/A"), severity=cash.get("deficit_severity", "WARNING"),
                trigger=cash.get("primary_deficit_trigger", "operational burn"),
            )
        else:
            tmpl = evaluate_persona_policy(prompt_type="DEFICIT_SAFE").get("guidance_text", "")
            head = tmpl.format(runway_desc=rd, cash_status=cash["cash_status"])
        return f"{head}{tail}"

    pred_line = f"\n- **Liquidity Forecast**: {pred.strip()}" if pred else ""
    target_line = f"\n- **Target Horizon**: {target.strip()}" if target else ""
    return (
        f"### Financial Diagnostic Summary\n\n"
        f"- **Current Balance**: {money(cash['current_balance'])} {cash['currency']}\n"
        f"- **Average Daily Burn**: {money(cash['average_daily_burn'])}/day\n"
        f"- **Estimated Historical Runway**: {rd} (Status: `{cash['cash_status']}`, Threshold: {cash['alert_threshold_days']} days)"
        f"{pred_line}{target_line}"
    )


def underwriting_base_reply(uw: Dict[str, Any]) -> str:
    dossier, options = uw["dossier"], uw["matched_options"]
    top = options[0] if options else None
    opt_summary = (
        f"Top matched facility is {top['facility_name']} from {top['provider']} "
        f"at {top['apr_percent']}% APR (Max: {money(top['max_amount'])})."
        if top
        else "No non-predatory credit facilities currently meet the underwriting criteria."
    )
    return (
        f"### Credit Underwriting Assessment\n\n"
        f"- **Underwriting evaluation complete**. Classification: `{dossier['risk_tier']}`\n"
        f"- **Daily Average Balance (DAB)**: {money(dossier['daily_average_balance'])}\n"
        f"- **Maximum Qualified Limit**: {money(dossier['max_qualified_limit'])}\n"
        f"- **Matched Facility**: {opt_summary}\n\n"
        "To apply, request staging for the chosen facility."
    )


# ==============================================================================
# Cash diagnostic prose
# ==============================================================================

TRIGGER_PHRASES = {
    "OPERATING_BURN": ["day-to-day operating burn", "ongoing operating costs outrunning receipts"],
    "RENT": ["the recurring rent payment", "the monthly rent obligation"],
    "DEBT_SERVICE": ["scheduled loan repayments", "the term loan repayment schedule"],
    "EXISTING_OVERDRAFT": ["the account already being overdrawn", "the existing overdraft"],
}

ACTIONS = {
    "critical": [
        "Stage the {bridge} working capital draw this week so it is in place before {ddate}.",
        "Chase your largest open invoices today and stage a {bridge} bridge for your approval before {ddate}.",
        "Hold non-essential supplier payments and request staging for a {bridge} bridge facility now.",
        "Request staging for the {bridge} bridge now; it only executes after you approve it.",
    ],
    "warning": [
        "Start collection calls on overdue invoices now and line up a working capital line before {ddate}.",
        "Push the next large supplier payment out where terms allow, and get a credit line pre-qualified before {ddate}.",
        "Run the credit underwriting check this week so a facility is ready well before {ddate}.",
    ],
    "watch_deficit": [
        "Tighten collections over the next few weeks and decide which recurring costs can be cut.",
        "Use the lead time to renegotiate supplier terms and bring receivables in faster.",
        "Set a weekly cash review and get a credit line pre-qualified while the pressure is still distant.",
    ],
    "watch": [
        "Bring forward collections on open invoices and review your largest recurring outflows this month.",
        "Ask your biggest customers for faster payment terms and trim discretionary spend before the runway shortens.",
        "Set a weekly cash review so the burn does not drift higher unnoticed.",
        "Get a working capital line pre-qualified now, while the numbers still support good terms.",
    ],
    "no_burn": [
        "Consider sweeping cash beyond your operating reserve into a money market account so it earns yield.",
        "Use this position to set up a credit line now, before you need one.",
        "Keep collections on their current schedule and decide how much surplus cash should be put to work.",
    ],
    "nonpositive": [
        "Fund the overdraft first, from incoming receivables or a staged bridge facility, before fees and returned payments pile up.",
        "Call your largest debtors today and pause every payment that is not payroll or tax until the account is back above zero.",
    ],
}


def cash_facts(cash: Dict[str, Any]) -> Dict[str, Any]:
    explanation = cash.get("predictive_explanation") or ""
    reserve = re.search(r"Projected 90-day reserve: (\$[-\d,]+\.\d{2})", explanation)
    has_def = bool(cash.get("has_projected_deficit"))
    severity = cash.get("deficit_severity") or "SAFE"
    if cash["cash_status"] == "CASH_NONPOSITIVE":
        situation = "nonpositive"
    elif has_def and severity == "CRITICAL":
        situation = "critical"
    elif has_def and severity == "WARNING":
        situation = "warning"
    elif has_def:
        situation = "watch_deficit"
    elif cash["cash_status"] == "NO_BURN":
        situation = "no_burn"
    else:
        situation = "watch"
    return {
        "bal": money(cash["current_balance"]),
        "cur": cash["currency"],
        "burn": money(cash["average_daily_burn"]),
        "runway": cash["runway_days"],
        "status": cash["cash_status"],
        "thr": cash["alert_threshold_days"],
        "infl": money(cash["gross_inflows"]),
        "outf": money(cash["gross_outflows"]),
        "net": money(cash["net_period_change"]),
        "net_negative": Decimal(str(cash["net_period_change"])) < 0,
        "has_def": has_def,
        "sev": severity,
        "short": money(cash.get("projected_shortfall_amount") or "0"),
        "bridge": money(cash.get("recommended_bridge_amount") or cash.get("projected_shortfall_amount") or "0"),
        "ddate": cash.get("projected_deficit_date"),
        "ddays": cash.get("days_until_deficit"),
        "trigger": cash.get("primary_deficit_trigger") or "OPERATING_BURN",
        "reserve": reserve.group(1) if reserve else None,
        "hd": cash.get("target_horizon_days"),
        "hdate": cash.get("target_horizon_date"),
        "hbal": money(cash["forecast_target_balance"]) if cash.get("forecast_target_balance") is not None else None,
        "htier": cash.get("confidence_tier"),
        "situation": situation,
    }


def forecast_sentence(rng: random.Random, f: Dict[str, Any]) -> Optional[str]:
    """Deficit or safe-horizon sentence using only figures the predictive explanation prints."""
    trig = rng.choice(TRIGGER_PHRASES.get(f["trigger"], TRIGGER_PHRASES["OPERATING_BURN"]))
    if f["situation"] in ("critical", "warning") or (f["situation"] == "nonpositive" and f["ddate"] and f["sev"] in ("CRITICAL", "WARNING")):
        return pick(rng, [
            "The forecast flags a {short} shortfall on {ddate}, {ddays} days out, driven by {trig}.",
            "On the current pattern the account goes {short} short around {ddate}, mainly because of {trig}.",
            "The projection shows a {short} gap opening on {ddate}, and {trig} is the main cause.",
            "Expect a shortfall of {short} by {ddate} unless something changes; {trig} is behind it.",
        ], trig=trig, **f)
    if f["situation"] == "watch_deficit":
        return pick(rng, [
            "The forecast shows the account slipping into deficit in {ddays} days if nothing changes.",
            "Further out, the projection turns negative in {ddays} days, driven by {trig}.",
            "There is no immediate gap, but the forecast turns negative in {ddays} days.",
        ], trig=trig, **f)
    if f["reserve"]:
        return pick(rng, [
            "The 90-day forecast stays positive, with a projected reserve of {reserve}.",
            "No shortfall appears in the forecast window, and the projected 90-day reserve is {reserve}.",
            "Looking ahead, the account stays solvent through the forecast, ending near a {reserve} reserve.",
        ], **f)
    return None


def horizon_sentence(rng: random.Random, f: Dict[str, Any]) -> Optional[str]:
    if not f["hd"] or not f["hbal"]:
        return None
    return pick(rng, [
        "For day {hd} ({hdate}), the projected balance is {hbal}, at {htier} confidence.",
        "By {hdate}, day {hd} of the forecast, the balance is projected at {hbal}.",
        "On your {hd}-day horizon the forecast lands at {hbal} on {hdate}.",
        "Projected forward {hd} days to {hdate}, the balance would be {hbal}.",
    ], **f)


def status_sentence(rng: random.Random, f: Dict[str, Any]) -> str:
    status = f["status"]
    if status == "LOW_RUNWAY":
        return rng.choice([
            "The status is LOW_RUNWAY, meaning cash runs out before the minimum safe horizon.",
            "That earns a LOW_RUNWAY status: the runway is shorter than the alert threshold allows.",
            "LOW_RUNWAY status means this needs attention now, not next quarter.",
        ])
    if status == "WATCH":
        return rng.choice([
            "Status is WATCH: the balance covers near-term commitments, but it shrinks every day the burn continues.",
            "The WATCH status means you are above the alert threshold for now, while the balance keeps falling.",
            "That keeps you in WATCH status, safe for the moment but trending down.",
        ])
    if status == "NO_BURN":
        return rng.choice([
            "The status is NO_BURN, so the question is how to use surplus cash rather than how to protect it.",
            "With a NO_BURN status, cash is building rather than draining.",
        ])
    return rng.choice([
        "The CASH_NONPOSITIVE status means the account is at or below zero right now.",
        "Status is CASH_NONPOSITIVE: there is no cash buffer left to absorb the next payment.",
    ])


def finish(rng: random.Random, first: str, middle: List[Optional[str]], action: str, min_middle: int = 2) -> str:
    """Keeps 3-6 sentences: the answer, a shuffled subset of supporting sentences, then the action."""
    middle = [m for m in middle if m]
    keep = rng.randint(min(min_middle, len(middle)), min(4, len(middle))) if middle else 0
    picked = set(rng.sample(range(len(middle)), keep))
    return " ".join([first, *(m for i, m in enumerate(middle) if i in picked), action])


def bold_first_figure(rng: random.Random, text: str) -> str:
    """Bolds the headline figure in some replies, as the base persona asks, without making it a fixed habit."""
    if rng.random() > 0.35:
        return text
    match = re.search(r"\$-?[\d,]+\.\d{2}|\b\d+ days\b", text)
    if not match:
        return text
    return f"{text[:match.start()]}**{match.group(0)}**{text[match.end():]}"


def cash_reply(rng: random.Random, cash: Dict[str, Any], branch: str) -> Optional[str]:
    f = cash_facts(cash)
    sit = f["situation"]
    if f["has_def"] and not (f["ddate"] and f["ddays"] is not None):
        return None
    finite = f["runway"] is not None and sit not in ("no_burn", "nonpositive")
    action = pick(rng, ACTIONS[sit], **f)
    fc, hz = forecast_sentence(rng, f), horizon_sentence(rng, f)

    if branch == "RUNWAY":
        if finite:
            first = pick(rng, [
                "You have {runway} days of runway left at the current burn of {burn} a day.",
                "At {burn} of average daily burn, your {bal} balance lasts {runway} days.",
                "Cash lasts {runway} more days on the current pattern.",
                "Runway stands at {runway} days, with {bal} in the account and {burn} going out each day on average.",
                "Your current balance buys you {runway} days at today's burn rate.",
                "On today's numbers the money runs out in {runway} days.",
            ], **f)
            support = pick(rng, [
                "That is based on {bal} in the bank and an average burn of {burn} per day.",
                "The calculation divides your {bal} balance by the {burn} daily burn.",
            ], **f) if f["bal"] not in first else None
        elif sit == "no_burn":
            first = pick(rng, [
                "There is no runway limit right now because inflows covered outflows, so average daily burn is $0.00.",
                "Runway is open-ended: the business is cash positive, with {bal} in the account and no net daily burn.",
                "You are not burning cash, so runway is not the constraint; the balance sits at {bal}.",
            ], **f)
            support = None
        else:
            first = pick(rng, [
                "There is effectively no runway left: the balance is {bal} and the account is burning {burn} a day.",
                "Runway is gone for now, with the balance at {bal} against a daily burn of {burn}.",
            ], **f)
            support = None
        return bold_first_figure(rng, finish(rng, first, [support, status_sentence(rng, f), fc, hz], action))

    if branch == "BALANCE":
        first = pick(rng, [
            "You have {bal} {cur} in the account right now.",
            "Current balance is {bal}.",
            "The statement closes at {bal} {cur}.",
            "Cash on hand is {bal}.",
            "Your balance stands at {bal} as of the last transaction.",
        ], **f)
        net = pick(rng, [
            "Over the reviewed period the balance moved by {net}, so more cash left than came in.",
            "That reflects a net change of {net} across the statement, a net outflow.",
            "The account fell by {net} over the period you uploaded.",
        ] if f["net_negative"] else [
            "Over the reviewed period the balance moved by {net}, so the account grew.",
            "That includes a net gain of {net} across the statement.",
            "The account added {net} over the period you uploaded.",
        ], **f)
        return bold_first_figure(rng, finish(rng, first, [net, fc, hz], action, min_middle=1))

    if branch == "BURN":
        if f["status"] == "NO_BURN":
            first = pick(rng, [
                "There is no net burn: inflows of {infl} exceeded outflows of {outf}, so average daily burn is $0.00.",
                "Average daily burn is $0.00, because the {infl} coming in beat the {outf} going out.",
            ], **f)
            support = None
        else:
            first = pick(rng, [
                "You are burning {burn} a day on average.",
                "Average daily burn is {burn}, from {outf} of outflows against {infl} of inflows.",
                "Net burn runs at {burn} per day.",
                "The business spends {burn} more than it takes in on an average day.",
            ], **f)
            support = pick(rng, [
                "Outflows totalled {outf} against inflows of {infl} over the period.",
                "That comes from {outf} going out versus {infl} coming in.",
            ], **f) if f["outf"] not in first else None
        runway_s = pick(rng, [
            "At that pace the runway is {runway} days.",
            "That burn leaves {runway} days of runway.",
        ], **f) if finite else None
        return bold_first_figure(rng, finish(rng, first, [support, runway_s, status_sentence(rng, f), fc, hz], action))

    if branch == "ADVICE":
        if f["has_def"]:
            first = pick(rng, [
                "Stage a working capital bridge of {bridge} now; the forecast shows a {short} shortfall on {ddate}.",
                "Your priority is closing a projected {short} gap before {ddate}.",
                "Protect the next few weeks first: the account is heading for a {short} shortfall on {ddate}.",
                "The recommendation is a {bridge} bridge facility, because cash falls {short} short on {ddate}.",
            ], **f)
            trig = rng.choice(TRIGGER_PHRASES.get(f["trigger"], TRIGGER_PHRASES["OPERATING_BURN"]))
            why = pick(rng, [
                "The main driver is {trig}.",
                "The gap comes from {trig}, not a one-off payment.",
            ], trig=trig)
            action = pick(rng, [
                "Request staging for the {bridge} bridge now, and pair it with a push on overdue invoices.",
                "Ask me to stage the {bridge} facility; it only executes after your explicit approval.",
                "Chase receivables this week and stage the {bridge} bridge as a backstop.",
            ], **f)
            return bold_first_figure(rng, finish(rng, first, [why, status_sentence(rng, f), hz], action))
        if f["status"] == "WATCH":
            first = pick(rng, [
                "Speed up collections and line up a working capital line while you still have {runway} days of runway.",
                "Act on the burn now: {burn} a day leaves {runway} days of runway on {bal}.",
                "Your cash covers near-term needs, but at {burn} a day the {bal} balance only lasts {runway} days.",
            ], **f)
            return bold_first_figure(rng, finish(rng, first, [status_sentence(rng, f), fc, hz], pick(rng, ACTIONS["watch"], **f)))
        if f["status"] != "NO_BURN":
            return None
        first = pick(rng, [
            "Your position is healthy: {bal} in the bank and no net burn.",
            "There is no cash pressure to fix; the balance is {bal} and the business is cash positive.",
            "Cash is in good shape, with {bal} on hand and inflows covering outflows.",
        ], **f)
        return bold_first_figure(rng, finish(rng, first, [status_sentence(rng, f), fc, hz], action, min_middle=1))

    if branch == "DEFICIT":
        if f["has_def"]:
            first = pick(rng, [
                "Yes. The forecast shows a {short} shortfall in {ddays} days, on {ddate}.",
                "A deficit is coming: the account runs {short} short by {ddate}.",
                "You are on track to go negative in {ddays} days ({ddate}), with a projected shortfall of {short}.",
                "The early warning is live, with a {short} gap projected for {ddate}.",
            ], **f)
            sev = pick(rng, [
                "Severity is {sev}, and {trig} is the primary driver.",
                "The engine rates it {sev}; the cause is {trig}.",
            ], sev=f["sev"], trig=rng.choice(TRIGGER_PHRASES.get(f["trigger"], TRIGGER_PHRASES["OPERATING_BURN"])))
            return bold_first_figure(rng, finish(rng, first, [sev, hz], action, min_middle=1))
        first = pick(rng, [
            "No. No deficit shows up over the projected horizon.",
            "No immediate overdraft risk shows up in the forecast.",
            "The projection stays positive, so no shortfall is expected in the forecast window.",
        ], **f)
        if fc:
            first, fc = f"{first} {fc}", None
        runway_s = pick(rng, [
            "Runway stands at {runway} days with a {status} status.",
            "You have {runway} days of runway on the current pattern.",
        ], **f) if finite else rng.choice([
            "The business is cash positive, so runway is open-ended.",
            "With no net burn, runway is not a constraint.",
        ])
        return bold_first_figure(rng, finish(rng, first, [runway_s, fc, hz], action, min_middle=1))

    # SUMMARY: the only branch that shows the alert threshold, which the model previously misread as a buffer.
    if finite:
        first = pick(rng, [
            "You have {bal} in the bank and burn {burn} a day, which gives {runway} days of runway.",
            "Runway is {runway} days: {bal} on hand against an average daily burn of {burn}.",
            "The statement shows {bal} in cash, {burn} of daily burn and {runway} days of runway.",
            "At {burn} a day, your {bal} balance covers {runway} days.",
        ], **f)
    elif sit == "no_burn":
        first = pick(rng, [
            "You have {bal} in the bank and no net burn, so runway is open-ended.",
            "The business is cash positive: {bal} on hand and an average daily burn of $0.00.",
        ], **f)
    else:
        first = pick(rng, [
            "The account is at {bal} with {burn} of average daily burn, so there is no runway left.",
            "Cash is exhausted: the balance reads {bal} while the business burns {burn} a day.",
        ], **f)
    thr_def = pick(rng, [
        "The {thr}-day figure is the alert threshold, the minimum runway before a warning fires, not cash held in reserve.",
        "Read the {thr}-day threshold as a tripwire: it marks the shortest runway considered safe, not a buffer you hold.",
        "The {thr}-day alert threshold is a warning line for runway, not an amount of money set aside.",
    ], **f)
    if f["status"] == "LOW_RUNWAY":
        thr_rel = "Your runway is below that line, which is why the status reads LOW_RUNWAY."
    elif f["status"] == "WATCH":
        thr_rel = rng.choice([
            "Your runway clears that line, so the status is WATCH rather than LOW_RUNWAY.",
            "You are above it for now, hence the WATCH status.",
        ])
    elif f["status"] == "NO_BURN":
        thr_rel = "With no burn, that threshold does not come into play."
    else:
        thr_rel = "The CASH_NONPOSITIVE status overrides it, because the balance is already at or below zero."
    body = [f"{thr_def} {thr_rel}"] if rng.random() < 0.7 else []
    text = finish(rng, first, [*body, fc, hz], action, min_middle=1)
    return bold_first_figure(rng, text)


CASH_QUESTIONS = {
    "RUNWAY": [
        "How long will my cash last?", "How many days of runway do we have left?", "When do we run out of money?",
        "How much runway is left at this burn?", "How long can we keep operating before cash runs out?",
        "How many days until the money runs out?", "How long will our cash runway last?", "What's our cash runway looking like?",
        "how long does my cash last", "When will we run out of cash at this rate?", "How many days of cash do we have?",
        "What is our projected cash runway on this statement?", "Can you estimate how many weeks of runway we have?",
        "How much operational runway remains before we hit zero?", "Are we close to running out of cash?",
        "Give me an assessment of our current runway.", "At our current net burn, how many days do we survive?",
        "whats our cash runway", "calculate our runway in days", "how many days of expenses can our balance cover?",
    ],
    "BALANCE": [
        "What's my current balance?", "How much cash do we have right now?", "What is our cash balance?",
        "How much money is in the account?", "Show me where our cash position stands.", "What's the closing balance on the statement?",
        "how much cash is in the bank", "What's our balance today?", "Tell me our current cash balance.",
        "What is our verified statement ending balance?", "How much liquid cash is currently available in the account?",
        "Can you confirm our current cash balance from the transactions?", "What did the account close at on the latest statement?",
        "whats our bank balance", "where does our cash stand right now", "check our liquid cash balance",
    ],
    "BURN": [
        "What's our burn rate?", "What is our average daily burn?", "How much are we burning each day?",
        "Are our outflows bigger than inflows?", "What's the daily burn rate?", "How much cash are we burning?",
        "what is my burn", "Show me our burn rate.", "How bad is our cash burn?",
        "What is our daily net cash burn velocity?", "How much cash does the business consume on an average day?",
        "Can you breakdown our net burn rate across the statement period?", "Are operating outflows outstripping customer deposits?",
        "whats our daily cash drain", "calculate our net daily burn", "how fast are we spending cash every day?",
    ],
    "ADVICE": [
        "Any advice on our cash position?", "How do I improve our liquidity?", "What's your advice on our cash flow?",
        "Give me advice on managing our cash.", "How can I improve cash flow?", "What should we do to improve liquidity?",
        "Any recommendations to improve our cash position?", "advice on our finances please",
        "What operational steps should we take to protect our cash buffer?", "How can we stabilize our liquidity heading into next quarter?",
        "What recommendations do you have to optimize our working cash?", "How do we improve our cash reserves based on this statement?",
        "give me actionable CFO advice on our cash", "what are the top priorities to fix our cash flow?",
    ],
    "DEFICIT": [
        "Are we heading for a cash shortfall?", "Will we go negative in the next few months?", "When could we hit a cash deficit?",
        "Is a cash deficit coming?", "Will we have a cash shortfall?", "Are we going to run a deficit?",
        "Do we face a shortfall this quarter?", "Is there a deficit coming?", "Will we go into overdraft?",
        "Does the predictive model detect an upcoming cash deficit?", "When is our account projected to breach zero balance?",
        "Are we at risk of an overdraft in the next 30 to 60 days?", "Will customer inflows cover our upcoming obligations?",
        "is an overdraft projected for our account?", "will we run out of money next month?",
    ],
    "SUMMARY": [
        "Give me a financial health check.", "Review my statement and tell me how we're doing.", "Can you audit this statement?",
        "How are we doing financially?", "Give me the big picture on our cash.", "Summarize our financial position.",
        "Check our financial health.", "What does this statement tell you?",
        "Can you run a full liquidity diagnosis on our uploaded transactions?", "Provide an executive cash overview from this statement.",
        "Audit our cash runway, burn rate, and balance in one summary.", "What is the overall financial diagnosis of our business?",
    ],
}
HORIZON_SUFFIXES = [
    " And where will we be in {d} days?", " Also, what does the balance look like in {d} days?",
    " Include a {d}-day forecast.", " What about {d} days from now?",
    " Can you project out {d} days?", " Looking ahead {d} days, what is the position?",
]
QUESTION_PREFIXES = [
    "", "Can you check: ", "Quick question: ", "Looking at our bank statement, ",
    "As our fractional CFO, ", "Based on recent transactions, ", "For our company, ",
    "Could you verify: ", "I need to know: ", "Please audit: ",
]


def build_cash_rows(rng: random.Random, statements: int) -> List[Dict[str, Any]]:
    rows = []
    usable = {b: [q for q in qs if cash_branch(q) == b] for b, qs in CASH_QUESTIONS.items()}
    for _ in range(statements):
        csv = make_statement(rng, rng.choices(list(PROFILES), weights=PROFILE_WEIGHTS)[0])
        horizon = rng.choice([None, None, rng.choice([14, 21, 30, 45, 60, 75])])
        for branch in rng.sample(list(usable), 2):
            if not usable[branch]:
                continue
            base_q = rng.choice(usable[branch])
            prefix = rng.choice(QUESTION_PREFIXES) if rng.random() < 0.4 else ""
            candidate = f"{prefix}{base_q}" if prefix else base_q
            if horizon:
                cand_with_hz = candidate + rng.choice(HORIZON_SUFFIXES).format(d=horizon)
                if cash_branch(cand_with_hz) == branch:
                    candidate = cand_with_hz
            question = candidate if cash_branch(candidate) == branch else base_q
            day_match = re.search(r"\b(\d{1,4})\s*[- ]*(?:day|days)\b", question, re.IGNORECASE)
            cash = tool_analyze_cash_flow(csv, target_horizon_days=int(day_match.group(1)) if day_match else None)
            reply = cash_reply(rng, cash, branch)
            if reply:
                base = cash_base_reply(cash, branch)
                sys_prompt = append_reference_cards(get_cash_diagnostic_prompt(base), question)
                rows.append(make_row(sys_prompt, question, reply, base, f"cash:{branch}"))
    return rows


# ==============================================================================
# Credit underwriting prose (statement-based)
# ==============================================================================

UW_QUESTIONS = [
    "Can we qualify for a loan?", "How much can we borrow?", "What financing options do we have?", "What credit line can we get?",
    "Do we qualify for working capital financing?", "Can I get a business loan?", "What loan options are available to us?",
    "Are we eligible for financing?", "What kind of credit can we access?", "How much financing could we get?",
    "Show me our financing options.", "can we get a credit line", "What funding can we qualify for?",
    "What commercial credit limit does our bank statement support?", "Can we obtain a non-predatory line of credit?",
    "What is our borrowing capacity based on our Daily Average Balance?", "Do we qualify for prime rates or conditional terms?",
    "How large of an accounts receivable line can we qualify for?", "Review our credit eligibility based on our cash flow.",
    "What working capital options can we access today?", "Can we get pre-qualified financing on this statement?",
]
TIER_MEANING = {
    "PRIME": ["PRIME means lenders see steady balances and low default risk.", "A PRIME rating gets you the cheapest facilities on offer."],
    "NEAR_PRIME": ["NEAR_PRIME means you qualify, but with tighter limits than a prime borrower.", "At NEAR_PRIME, lenders will lend but price in more caution."],
    "HIGH_RISK": ["HIGH_RISK reflects thin or volatile balances, so terms will be limited.", "A HIGH_RISK rating means most lenders will want stronger balances first."],
}


def underwriting_reply(rng: random.Random, uw: Dict[str, Any]) -> str:
    d, options = uw["dossier"], uw["matched_options"]
    f = {"tier": d["risk_tier"], "limit": money(d["max_qualified_limit"]), "dab": money(d["daily_average_balance"])}
    if Decimal(str(d["max_qualified_limit"])) == 0:
        first = pick(rng, [
            "Classification is {tier} and the maximum qualified limit is {limit}, so no lender will extend credit on this statement.",
            "The underwriting comes back {tier} with a qualified limit of {limit}, which means no facility is available yet.",
            "Right now the statement supports no borrowing: the limit is {limit} at a {tier} rating.",
            "A {limit} qualified limit and a {tier} rating mean lenders would decline today.",
        ], **f)
    else:
        first = pick(rng, [
            "You qualify as {tier}, with a maximum qualified limit of {limit}.",
            "The underwriting puts you in the {tier} tier, with up to {limit} available.",
            "Your statement supports a {tier} rating and a borrowing ceiling of {limit}.",
            "You can borrow up to {limit}, and the risk classification is {tier}.",
            "Classification is {tier} and the maximum qualified limit is {limit}.",
            "Up to {limit} is available to you at a {tier} risk rating.",
            "Lenders would see you as {tier}, good for a limit of up to {limit}.",
        ], **f)
    dab = pick(rng, [
        "That limit is sized from your Daily Average Balance of {dab}.",
        "Lenders size the line off your DAB, which is {dab} on this statement.",
        "Your Daily Average Balance (DAB) of {dab} is what drives that ceiling.",
    ], **f)
    meaning = rng.choice(TIER_MEANING.get(f["tier"], TIER_MEANING["NEAR_PRIME"]))
    if options:
        top = options[0]
        f.update(name=top["facility_name"], provider=top["provider"], apr=top["apr_percent"], max=money(top["max_amount"]))
        facility = pick(rng, [
            "The best match is the {name} from {provider} at {apr}% APR, up to {max}.",
            "{provider} offers the top-matched {name} at {apr}% APR.",
            "Top of the list is the {name} at {apr}% APR from {provider}.",
        ], **f)
        apr_note = None if top["is_predatory"] else rng.choice([
            "That APR passes the non-predatory check.",
            "The rate sits within non-predatory lending limits.",
            "That pricing is non-predatory.",
        ])
        action = pick(rng, [
            "If you want to proceed, ask me to stage the {name} application; nothing executes until you approve it.",
            "Proposals are staged for your review first and only go ahead with your explicit approval.",
            "Say the word and I will stage a proposal for the {name}; it waits for your sign-off.",
            "Request staging for the {name} when ready, and it will sit in draft until you approve it.",
        ], **f)
    else:
        facility = "No non-predatory facility meets the underwriting criteria right now."
        apr_note = None
        action = rng.choice([
            "Build a few months of steadier balances, then rerun the underwriting before applying.",
            "Focus on lifting your average balance first; I can rerun the check once the next statement is in.",
        ])
    closing = f"{facility} {apr_note}" if apr_note else facility
    return bold_first_figure(rng, finish(rng, first, [dab, meaning], f"{closing} {action}", min_middle=1))


def build_underwriting_rows(rng: random.Random, statements: int) -> List[Dict[str, Any]]:
    usable = [q for q in UW_QUESTIONS if route(q, True)[0] == "CREDIT_UNDERWRITING" and not route(q, True)[2]]
    rows = []
    for _ in range(statements):
        csv = make_statement(rng, rng.choices(list(PROFILES), weights=PROFILE_WEIGHTS)[0])
        uw = tool_underwrite_credit(csv, nsf_count=rng.choice([0, 0, 0, 1, 2, 3, 5]))
        base = underwriting_base_reply(uw)
        base_q = rng.choice(usable)
        prefix = rng.choice(QUESTION_PREFIXES) if rng.random() < 0.35 else ""
        cand = f"{prefix}{base_q}" if prefix else base_q
        q = cand if (route(cand, True)[0] == "CREDIT_UNDERWRITING" and not route(cand, True)[2]) else base_q
        sys_prompt = append_reference_cards(get_credit_underwriting_prompt(base), q)
        rows.append(make_row(sys_prompt, q, underwriting_reply(rng, uw), base, f"underwriting:{uw['dossier']['risk_tier']}"))
    return rows


# ==============================================================================
# Quantitative calculations (base_reply captured from the real subagent handlers)
# ==============================================================================


def k(rng: random.Random, lo: int, hi: int, step: int = 1000) -> int:
    return rng.randrange(lo, hi, step)


def usd(n: int) -> str:
    return f"${n:,}"


QUANT_SPECS: List[Dict[str, Any]] = [
    {
        "sub": "DSCR", "name": "your DSCR", "head": "DSCR Metric", "tier": "Underwriting Status",
        "support": [("Net Operating Income (NOI)", "net operating income"), ("Annual Debt Service", "annual debt service")],
        "params": lambda r: {"noi": usd(k(r, 60_000, 600_000)), "ds": usd(k(r, 30_000, 400_000))},
        "questions": ["What is our DSCR if annual NOI is {noi} and debt payments are {ds}?", "Calculate DSCR with NOI {noi} and annual debt service {ds}.", "Our net operating income is {noi} and debt service is {ds}. What's the DSCR?"],
        "meaning": {"good": "Lenders read that as comfortable cover for principal and interest.", "mid": "That clears the bar, but there is little room if income dips.", "bad": "Lenders will see that cover as too thin for new debt."},
        "action": {"good": ["You can approach lenders with confidence; keep NOI steady through the application.", "Use this cover to negotiate better pricing on your next facility."], "bad": ["Pay down the most expensive debt or lift operating income before taking on more borrowing.", "Hold off on new debt until operating income or the repayment schedule improves."]},
    },
    {
        "sub": "FCCR", "name": "your fixed charge coverage", "head": "FCCR Metric", "tier": "Covenant Approval Tier",
        "support": [("Annual EBITDA", "EBITDA"), ("Fixed Operational Charges", "fixed charges"), ("Total Annual Debt Service", "debt service")],
        "params": lambda r: {"e": usd(k(r, 80_000, 800_000)), "fc": usd(k(r, 10_000, 120_000)), "ds": usd(k(r, 20_000, 300_000))},
        "questions": ["Calculate FCCR for EBITDA {e}, fixed charges {fc}, and debt service {ds}", "What's our fixed charge coverage ratio with EBITDA {e}, fixed charges {fc} and debt service {ds}?"],
        "meaning": {"good": "Leases and debt are both covered with room to spare.", "mid": "Coverage is adequate, but a weak quarter would squeeze it.", "bad": "Fixed charges and debt eat too much of EBITDA for lenders to be comfortable."},
        "action": {"good": ["Keep fixed commitments flat while EBITDA grows, and the covenant stays safe.", "You have room to take on a modest facility if needed."], "bad": ["Renegotiate leases or stretch debt terms before adding any new fixed commitment.", "Cut fixed charges first; that improves the ratio fastest."]},
    },
    {
        "sub": "DEBT_CAPACITY", "name": "your maximum prudent debt capacity", "head": "Maximum Prudent Debt Capacity",
        "support": [("Net Operating Income (NOI)", "net operating income"), ("Target DSCR Covenant", "target DSCR"), ("Assumed Facility APR", "assumed APR")],
        "params": lambda r: {"noi": usd(k(r, 50_000, 500_000)), "dscr": r.choice(["1.25x", "1.35x", "1.5x"])},
        "questions": ["What is our maximum prudent borrowing capacity with {noi} NOI at {dscr} DSCR?", "How much can we safely borrow with NOI of {noi} and a {dscr} DSCR target?"],
        "meaning": {"any": "Borrowing above that ceiling would push coverage below the covenant you set."},
        "action": {"any": ["Treat that figure as the ceiling and size any facility comfortably below it.", "Ask me to match facilities within that limit when you are ready to borrow."]},
    },
    {
        "sub": "AMORTIZATION", "name": "the monthly payment", "head": "Fixed Monthly Payment", "unit": " a month",
        "support": [("Total Interest Cost", "total interest"), ("Total Loan Obligation", "total repayment")],
        "params": lambda r: {"p": usd(k(r, 20_000, 400_000)), "rate": r.choice([6, 7, 8, 9, 10, 11, 12]), "m": r.choice([12, 24, 36, 48, 60])},
        "questions": ["Calculate monthly payment for a {p} commercial loan at {rate}% interest over {m} months", "What's the monthly repayment on a {p} loan at {rate}% for {m} months?"],
        "meaning": {"any": "Make sure that payment fits inside your monthly operating cash flow before signing."},
        "action": {"any": ["Compare the payment with your average monthly net inflow, then request staging if it fits.", "If the payment feels tight, test a longer term to lower it."]},
    },
    {
        "sub": "FACTORING", "name": "your total net cash after collection", "head": "Total Net Proceeds After Collection",
        "support": [("Cash Received Now", "cash received now"), ("Factoring Discount Fee", "fee"), ("True Annualized APR", "true APR")],
        "params": lambda r: {"inv": usd(k(r, 10_000, 250_000)), "adv": r.choice([75, 80, 85, 90]), "fee": r.choice([1, 2, 3, 4]), "d": r.choice([30, 45, 60, 90])},
        "questions": ["Factor a {inv} invoice with {adv}% advance, {fee}% discount fee, and {d} days collection", "What do we net if we factor a {inv} invoice at {adv}% advance with a {fee}% fee over {d} days?"],
        "meaning": {"any": "The annualized APR is the number to compare against a bank line, not the headline fee."},
        "action": {"any": ["Compare that APR with a working capital line before you commit.", "Request staging if the APR beats your other options; it waits for your approval."]},
    },
    {
        "sub": "WCR", "name": "your working capital requirement", "head": "Net Working Capital Requirement", "tier": "Liquidity Posture",
        "support": [("Accounts Receivable (AR)", "receivables"), ("Inventory", "inventory"), ("Accounts Payable (AP)", "payables")],
        "params": lambda r: {"ar": usd(k(r, 10_000, 300_000)), "inv": usd(k(r, 5_000, 200_000)), "ap": usd(k(r, 5_000, 200_000))},
        "questions": ["What is our working capital requirement if receivables are {ar}, inventory {inv}, and payables {ap}?", "Calculate WCR with receivables {ar}, inventory {inv} and payables {ap}."],
        "meaning": {"any": "That is the cash tied up in running the business before customers pay you."},
        "action": {"any": ["Shorten collection terms or carry less stock to free part of that cash.", "Negotiate longer supplier terms to offset the amount tied up."]},
    },
    {
        "sub": "OCF_RATIO", "name": "your operating cash flow ratio", "head": "Operating Cash Flow Ratio", "tier": "Solvency Classification",
        "support": [("Operating Cash Flow", "operating cash flow"), ("Current Liabilities", "current liabilities")],
        "params": lambda r: {"ocf": usd(k(r, 20_000, 400_000)), "cl": usd(k(r, 20_000, 300_000))},
        "questions": ["Calculate our operating cash flow ratio for OCF {ocf} and current liabilities {cl}", "What's the OCF ratio if operating cash flow is {ocf} and current liabilities are {cl}?"],
        "meaning": {"good": "Operations alone cover short-term obligations.", "mid": "Operations roughly cover short-term debts, with little slack.", "bad": "Operating cash does not cover short-term debts, so you depend on reserves or credit."},
        "action": {"good": ["Keep this cushion as you plan any new short-term borrowing."], "bad": ["Bring receivables in faster and push out non-urgent payables to close the gap."]},
    },
    {
        "sub": "BREAK_EVEN", "name": "your break-even revenue", "head": "Break-Even Revenue Requirement",
        "support": [("Fixed Operating Overhead", "fixed costs"), ("Contribution Margin Ratio", "contribution margin")],
        "params": lambda r: {"fc": usd(k(r, 10_000, 200_000)), "m": r.choice([20, 25, 30, 35, 40, 45, 50, 60])},
        "questions": ["What is our break-even if fixed costs are {fc} and margin is {m}%?", "Calculate break-even revenue for fixed costs {fc} at a {m}% contribution margin."],
        "meaning": {"any": "Every sale above that line adds to operating profit; below it, you lose money."},
        "action": {"any": ["Track monthly revenue against that line and cut fixed costs if you keep falling short.", "Lifting the margin even slightly lowers that threshold faster than cutting volume targets."]},
    },
    {
        "sub": "BREAK_EVEN_UNITS", "name": "your break-even volume", "head": "Required Sales Volume to Break Even",
        "support": [("Fixed Operating Overhead", "fixed overhead"), ("Unit Contribution Margin", "unit contribution margin")],
        "params": lambda r: (lambda price: {"fc": usd(k(r, 10_000, 200_000)), "p": usd(price), "v": usd(r.randrange(price // 5, price * 4 // 5))})(r.randrange(20, 500, 5)),
        "questions": ["How many units must we sell to break even if fixed costs are {fc}, price {p}, and variable cost {v}?", "Break-even units for fixed costs {fc}, selling price {p} and variable cost {v}?"],
        "meaning": {"any": "Units sold beyond that volume turn into profit."},
        "action": {"any": ["Compare that volume with last quarter's sales to see how close you are.", "Raise the price or cut unit costs if that volume is out of reach."]},
    },
    {
        "sub": "ATTRITION", "name": "the projected net deficit if that client leaves", "head": "Projected Net Deficit Under Loss", "unit": " a year", "tier": "Risk Classification",
        "support": [("Current Annual Inflows", "current revenue"), ("Lost Client Annual Share", "the client's revenue")],
        "params": lambda r: (lambda rev: {"rev": usd(rev), "c": usd(k(r, rev // 10, rev // 2)), "exp": usd(k(r, rev * 6 // 10, rev))})(k(r, 150_000, 900_000)),
        "questions": ["What is the cash flow impact if we lose our largest client who pays {c} out of {rev} revenue with {exp} annual expenses?"],
        "meaning": {"any": "That gap would have to be covered by cuts, new clients or credit."},
        "action": {"any": ["Diversify now: start replacing part of that client's revenue before it is at risk.", "Build a cost-cut plan you can trigger the day that client gives notice."]},
    },
    {
        "sub": "CURRENT_RATIO", "name": "your current ratio", "head": "Current Ratio", "tier": "Working Capital Solvency",
        "support": [("Current Assets", "current assets"), ("Current Liabilities", "current liabilities")],
        "params": lambda r: {"a": usd(k(r, 30_000, 600_000)), "l": usd(k(r, 30_000, 400_000))},
        "questions": ["What is our current ratio for assets {a} and liabilities {l}?", "Calculate the current ratio with current assets {a} and current liabilities {l}."],
        "meaning": {"good": "Short-term assets comfortably cover what is due within a year.", "mid": "Assets cover obligations, but the buffer is thin.", "bad": "Short-term obligations exceed liquid assets, which lenders flag quickly."},
        "action": {"good": ["Keep idle current assets from piling up; surplus cash could earn yield."], "bad": ["Convert receivables to cash faster and avoid new short-term debt until the ratio recovers."]},
    },
    {
        "sub": "QUICK_RATIO", "name": "your quick ratio", "head": "Quick Ratio", "tier": "Immediate Liquidity Tier",
        "support": [("Quick Liquid Assets", "quick assets"), ("Current Liabilities", "current liabilities")],
        "params": lambda r: {"a": usd(k(r, 50_000, 600_000)), "i": usd(k(r, 5_000, 150_000)), "l": usd(k(r, 30_000, 400_000))},
        "questions": ["Calculate quick ratio with assets {a}, inventory {i}, and liabilities {l}", "What's our acid test ratio with current assets {a}, inventory {i} and liabilities {l}?"],
        "meaning": {"good": "You can meet immediate bills without selling inventory.", "mid": "You can just about cover bills without selling stock.", "bad": "Paying immediate bills would depend on selling inventory."},
        "action": {"good": ["Hold this level of liquidity through your slow season."], "bad": ["Build cash or cut short-term liabilities so bills do not depend on stock sales."]},
    },
    {
        "sub": "DEBT_TO_EQUITY", "name": "your debt-to-equity ratio", "head": "Debt-to-Equity Ratio", "tier": "Leverage Profile",
        "support": [("Total Debt Obligations", "total debt"), ("Total Shareholder Equity", "equity")],
        "params": lambda r: {"d": usd(k(r, 20_000, 900_000)), "e": usd(k(r, 50_000, 900_000))},
        "questions": ["Calculate debt to equity for debt {d} and equity {e}", "What's our D/E ratio with total debt {d} and shareholder equity {e}?"],
        "meaning": {"good": "Debt is modest next to equity, which leaves borrowing room.", "mid": "Debt is moderate next to equity; much more would start to worry lenders.", "bad": "Debt is heavy relative to equity, so lenders will price new credit higher."},
        "action": {"good": ["Use that headroom selectively for growth that pays back quickly."], "bad": ["Prioritise paying down debt or adding equity before new borrowing."]},
    },
    {
        "sub": "INTEREST_COVERAGE", "name": "your interest coverage", "head": "Interest Coverage Ratio", "tier": "Covenant Health Tier",
        "support": [("Operating Income (EBIT)", "EBIT"), ("Annual Interest Expense", "interest expense")],
        "params": lambda r: {"ebit": usd(k(r, 20_000, 500_000)), "i": usd(k(r, 5_000, 120_000))},
        "questions": ["What is our interest coverage with EBIT {ebit} and interest expense {i}?", "Calculate times interest earned for EBIT {ebit} and interest of {i}."],
        "meaning": {"good": "Operating income covers interest many times over.", "mid": "Interest is covered, though a dip in EBIT would tighten it.", "bad": "Interest takes too large a bite of operating income."},
        "action": {"good": ["Use this strength when negotiating rates on your next facility."], "bad": ["Refinance the most expensive debt or lift EBIT before borrowing more."]},
    },
    {
        "sub": "TRADE_CREDIT", "name": "the implied APR of skipping the discount", "head": "Annualized Implied APR", "tier": "Working Capital Recommendation Tier",
        "support": [("Gross Early Payment Savings", "early payment savings"), ("Net Financial Benefit", "net benefit")],
        "params": lambda r: {"t": r.choice(["2/10 net 30", "1/10 net 30", "2/10 net 45", "3/15 net 60", "1/15 net 45"]), "inv": usd(k(r, 10_000, 200_000)), "line": r.choice([7, 8, 9, 10, 12, 14])},
        "questions": ["Evaluate trade terms {t} for a {inv} invoice with a {line}% credit line"],
        "meaning": {"any": "Compare that implied APR with what your credit line costs to decide whether paying early wins."},
        "action": {"any": ["If the net benefit is positive, pay early using the cheaper credit line.", "Apply the same test to every supplier offering early-payment terms."]},
    },
    {
        "sub": "CASH_DRAG", "name": "your annual cash drag", "head": "Annual Cash Drag / Yield Loss", "unit": " a year", "tier": "Allocation Status",
        "support": [("Current Cash Balance", "cash balance"), ("Idle Surplus Cash", "idle surplus")],
        "params": lambda r: {"c": usd(k(r, 100_000, 2_000_000, 10_000)), "b": usd(k(r, 10_000, 150_000)), "y": r.choice(["3.5", "4", "4.5", "5"])},
        "questions": ["Calculate cash drag for cash balance {c} with monthly burn {b} at {y}% yield"],
        "meaning": {"any": "That is income you give up by leaving surplus cash idle."},
        "action": {"any": ["Sweep the surplus above your operating reserve into a money market account.", "Keep the reserve liquid and move only the idle surplus into yield."]},
    },
    {
        "sub": "LEASE_VS_BUY", "name": "the net advantage", "head": "Net Financial Advantage", "tier": "Decision Policy",
        "support": [("Present Value Cost (Leasing)", "present value cost of leasing"), ("Present Value Cost (Buying)", "present value cost of buying")],
        "params": lambda r: (lambda cost: {"cost": usd(cost), "lease": usd(k(r, cost // 6, cost // 3)), "y": r.choice([3, 4, 5]), "dr": r.choice([6, 7, 8, 9, 10])})(k(r, 40_000, 400_000)),
        "questions": ["Should we lease or buy equipment costing {cost} with lease payments of {lease} for {y} years at {dr}% discount rate?"],
        "meaning": {"any": "The cheaper option on a present value basis is the one the engine recommends."},
        "action": {"any": ["Go with the recommended option unless you need the equipment beyond the term.", "Check the lease terms for buyout clauses before you sign."]},
    },
    {
        "sub": "ALTMAN_Z_SCORE", "name": "your Altman Z'-Score", "head": "Altman Z'-Score", "tier": "Credit Distress Tier",
        "support": [("Working Capital", "working capital"), ("Total Liabilities", "total liabilities")],
        "params": lambda r: {"wc": usd(k(r, 10_000, 150_000)), "re": usd(k(r, 10_000, 200_000)), "ebit": usd(k(r, 5_000, 120_000)), "eq": usd(k(r, 40_000, 300_000)), "li": usd(k(r, 50_000, 400_000)), "rev": usd(k(r, 150_000, 1_200_000)), "as": usd(k(r, 120_000, 700_000))},
        "questions": [
            "Calculate Altman Z score: working capital {wc}, retained earnings {re}, EBIT {ebit}, equity {eq}, liabilities {li}, revenue {rev}, assets {as}",
            "What is our Altman Z'-Score with working capital {wc}, retained earnings {re}, EBIT {ebit}, equity {eq}, total debt {li}, revenue {rev}, and total assets {as}?",
            "Evaluate insolvency risk with Altman Z-score: WC {wc}, RE {re}, EBIT {ebit}, equity {eq}, liabilities {li}, sales {rev}, assets {as}",
            "Run an Altman Z financial distress audit for working capital {wc}, retained earnings {re}, EBIT {ebit}, shareholder equity {eq}, liabilities {li}, revenue {rev}, assets {as}."
        ],
        "meaning": {"good": "That sits in the safe zone, so insolvency risk is low.", "mid": "That is the grey zone: viable, but exposed to a revenue drop.", "bad": "That is the distress zone, which lenders treat as high insolvency risk."},
        "action": {"good": ["Recheck the score each year-end to catch any drift."], "bad": ["Shore up working capital and retained earnings before seeking new credit."]},
    },
    {
        "sub": "NET_DEBT_TO_EBITDA", "name": "your net debt to EBITDA", "head": "Net Debt to EBITDA Multiple", "tier": "Institutional Leverage Tier",
        "support": [("Net Debt", "net debt"), ("Annual Operating EBITDA", "EBITDA")],
        "params": lambda r: {"d": usd(k(r, 50_000, 900_000)), "c": usd(k(r, 5_000, 200_000)), "e": usd(k(r, 40_000, 400_000))},
        "questions": ["What is our Net Debt to EBITDA with debt {d}, cash {c}, and EBITDA {e}?"],
        "meaning": {"good": "Debt is low against earnings, leaving plenty of borrowing room.", "mid": "Debt is manageable against earnings, but close to where banks get cautious.", "bad": "Debt is high against earnings, so new borrowing will be hard to place."},
        "action": {"good": ["You can approach banks for growth capital from a strong position."], "bad": ["Pay debt down or grow EBITDA before asking for more credit."]},
    },
    {
        "sub": "DEBT_SERVICE_BURDEN", "name": "your debt service burden", "head": "Debt Service Burden", "tier": "Debt Service Tier",
        "support": [("Annual Debt Service Obligations", "annual debt payments"), ("Gross Commercial Revenue", "revenue")],
        "params": lambda r: {"ds": usd(k(r, 10_000, 200_000)), "rev": usd(k(r, 150_000, 1_500_000))},
        "questions": ["What is our debt service burden if annual debt payments are {ds} and revenue is {rev}?"],
        "meaning": {"good": "Debt payments take a small share of revenue.", "mid": "Debt payments are manageable but meaningful.", "bad": "Debt payments take too much of revenue for comfort."},
        "action": {"good": ["Keep new borrowing in proportion to revenue growth."], "bad": ["Refinance onto longer terms to lower annual payments."]},
    },
    {
        "sub": "ROIC", "name": "your return on invested capital", "head": "Return on Invested Capital (ROIC)", "tier": "Capital Efficiency Tier",
        "support": [("Net Operating Profit After Tax (NOPAT)", "NOPAT"), ("Total Invested Capital", "invested capital")],
        "params": lambda r: {"ebit": usd(k(r, 20_000, 400_000)), "d": usd(k(r, 20_000, 500_000)), "e": usd(k(r, 50_000, 600_000)), "c": usd(k(r, 5_000, 100_000))},
        "questions": ["Calculate ROIC for EBIT {ebit}, debt {d}, equity {e}, and cash {c}"],
        "meaning": {"good": "The business earns well above a typical cost of capital.", "mid": "Returns roughly match the cost of capital.", "bad": "Returns fall short of what the capital costs."},
        "action": {"good": ["Reinvest in the activities driving these returns."], "bad": ["Cut underused assets or lift margins before investing more capital."]},
    },
    {
        "sub": "ROA", "name": "your return on assets", "head": "Return on Assets (ROA)", "tier": "Asset Productivity Tier",
        "support": [("Annual Net Income", "net income"), ("Total Balance Sheet Assets", "total assets")],
        "params": lambda r: {"ni": usd(k(r, 5_000, 200_000)), "a": usd(k(r, 100_000, 1_500_000))},
        "questions": ["What is our ROA if net income is {ni} and total assets are {a}?", "Calculate return on assets with net income {ni} and total assets {a}."],
        "meaning": {"good": "Assets are working hard for the business.", "mid": "Asset returns are in a normal range.", "bad": "Assets are not producing much profit."},
        "action": {"good": ["Keep asset growth in line with profit growth."], "bad": ["Sell or repurpose idle assets to lift the return."]},
    },
    {
        "sub": "EVA", "name": "your economic value added", "head": "Economic Value Added (EVA)", "tier": "Economic Profit Status",
        "support": [("Net Operating Profit After Tax (NOPAT)", "NOPAT"), ("Capital Charge", "capital charge")],
        "params": lambda r: {"ebit": usd(k(r, 30_000, 400_000)), "ic": usd(k(r, 100_000, 2_000_000, 10_000)), "w": r.choice([7, 8, 9, 10, 11, 12])},
        "questions": ["Calculate EVA for EBIT {ebit}, invested capital {ic}, and {w}% WACC"],
        "meaning": {"good": "Operations earn more than the full cost of the capital they use.", "bad": "Operations do not yet cover the full cost of capital."},
        "action": {"good": ["Direct new capital to the units generating this surplus."], "bad": ["Shrink the capital base or improve margins until EVA turns positive."]},
    },
    {
        "sub": "FCFF", "name": "your free cash flow to the firm", "head": "Free Cash Flow to Firm (FCFF)", "tier": "Cash Flow Quality Status",
        "support": [("Operating Cash Flow (OCF)", "operating cash flow"), ("Capital Expenditures (CapEx)", "capital expenditure")],
        "params": lambda r: {"ocf": usd(k(r, 30_000, 500_000)), "cx": usd(k(r, 5_000, 200_000)), "i": usd(k(r, 2_000, 40_000))},
        "questions": ["Calculate free cash flow for OCF {ocf} and CapEx {cx} with {i} interest"],
        "meaning": {"good": "Operations fund investment with cash left over.", "bad": "Investment is consuming more cash than operations generate."},
        "action": {"good": ["Decide whether surplus cash goes to debt paydown, reserves or growth."], "bad": ["Phase capital spending until operating cash flow catches up."]},
    },
    {
        "sub": "WACC", "name": "your WACC", "head": "Weighted Average Cost of Capital (WACC)",
        "support": [("Equity Capital Value", "equity"), ("Total Debt Obligations", "debt")],
        "params": lambda r: {"e": usd(k(r, 100_000, 2_000_000, 10_000)), "ke": r.choice([10, 11, 12, 14, 15]), "d": usd(k(r, 50_000, 1_000_000, 10_000)), "kd": r.choice([5, 6, 7, 8, 9]), "t": r.choice([21, 25, 30])},
        "questions": ["Calculate WACC with equity {e} at {ke}%, debt {d} at {kd}%, and {t}% tax rate"],
        "meaning": {"any": "Any project needs to return more than that to create value."},
        "action": {"any": ["Use that rate as the hurdle when you compare investment options.", "Screen your next capital project against that hurdle before committing."]},
    },
    {
        "sub": "LTV_CAC", "name": "your LTV to CAC ratio", "head": "LTV to CAC Ratio", "tier": "Unit Economics Tier",
        "support": [("Customer Lifetime Value (LTV)", "lifetime value"), ("Customer Acquisition Cost (CAC)", "acquisition cost")],
        "params": lambda r: {"arpu": usd(k(r, 200, 5_000, 50)), "gm": r.choice([50, 60, 70, 75, 80, 85]), "ch": r.choice([5, 10, 15, 20, 25, 30]), "cac": usd(k(r, 100, 3_000, 50))},
        "questions": ["Calculate LTV/CAC for ARPU {arpu}, gross margin {gm}%, churn {ch}%, and CAC {cac}"],
        "meaning": {"good": "Each customer returns several times what it costs to win them.", "mid": "Unit economics work, though with modest headroom.", "bad": "You spend too much to acquire customers relative to what they return."},
        "action": {"good": ["Scale acquisition spend while watching that churn holds."], "bad": ["Cut acquisition spend or reduce churn before scaling marketing."]},
    },
    {
        "sub": "CAC_PAYBACK", "name": "your CAC payback period", "head": "CAC Payback Period", "tier": "Payback Velocity Tier",
        "support": [("Customer Acquisition Cost (CAC)", "acquisition cost"), ("Monthly Gross Profit per Account", "monthly gross profit per account")],
        "params": lambda r: {"arpu": usd(k(r, 20, 500, 5)), "gm": r.choice([50, 60, 70, 75, 80]), "cac": usd(k(r, 100, 4_000, 50))},
        "questions": ["Calculate CAC payback for monthly ARPU {arpu}, gross margin {gm}%, and CAC {cac}"],
        "meaning": {"good": "Sales spend comes back quickly, so growth does not strain cash.", "mid": "Payback is acceptable but ties up cash for a while.", "bad": "Sales spend takes too long to come back, which strains cash."},
        "action": {"good": ["You can fund growth from operating cash rather than credit."], "bad": ["Raise prices or lower acquisition cost to shorten the payback."]},
    },
    {
        "sub": "NRR", "name": "your net revenue retention", "head": "Net Revenue Retention (NRR)", "tier": "Retention Health Tier",
        "support": [("Starting Revenue Base", "starting revenue"), ("Ending Cohort Revenue", "ending cohort revenue")],
        "params": lambda r: {"s": usd(k(r, 100_000, 2_000_000, 10_000)), "x": usd(k(r, 5_000, 200_000)), "c": usd(k(r, 2_000, 80_000)), "ch": usd(k(r, 2_000, 120_000))},
        "questions": ["Calculate NRR for starting ARR {s}, expansion {x}, contraction {c}, and churn {ch}"],
        "meaning": {"good": "Existing customers grow revenue on their own.", "mid": "Retention is steady, without much expansion.", "bad": "The customer base is shrinking before new sales."},
        "action": {"good": ["Invest in account expansion; it is your cheapest growth."], "bad": ["Find out why accounts churn or downgrade before spending more on acquisition."]},
    },
    {
        "sub": "DUPONT_ROE", "name": "your DuPont ROE", "head": "Aggregate Return on Equity (ROE)", "tier": "Performance Policy Tier",
        "support": [("Annual Net Income", "net income"), ("Annual Gross Revenue", "revenue"), ("Asset Efficiency (Asset Turnover)", "asset turnover")],
        "params": lambda r: (lambda rev: {"ni": usd(k(r, rev // 20, rev // 4)), "rev": usd(rev), "a": usd(k(r, rev // 2, rev * 2)), "eq": usd(k(r, rev // 4, rev))})(k(r, 200_000, 2_000_000, 10_000)),
        "questions": [
            "Calculate DuPont ROE: net income {ni}, revenue {rev}, total assets {a}, equity {eq}",
            "What is our DuPont 3-stage ROE breakdown with net income {ni}, sales {rev}, total assets {a}, and equity {eq}?",
            "Run a DuPont ROE decomposition for net income of {ni}, commercial revenue of {rev}, assets {a}, and equity {eq}.",
            "Evaluate return on equity through DuPont 3-stage analysis with {ni} net profit, {rev} gross revenue, {a} assets, and {eq} equity."
        ],
        "meaning": {
            "good": "Operations generate strong, balanced returns on shareholder equity.",
            "mid": "Returns on equity are moderate, with room to improve margin or asset turns.",
            "bad": "Returns fall short of acceptable cost of equity; margins or asset turnover are lagging."
        },
        "action": {
            "good": ["Reinvest operating profit into the product lines driving these margins.", "Maintain this leverage balance while expanding commercial sales."],
            "bad": ["Lift operating margins or optimize asset turnover to improve equity returns.", "Review low-margin customer accounts to prevent margin compression."]
        },
    },
    {
        "sub": "DCF_VALUATION", "name": "your implied DCF enterprise value", "head": "Enterprise Value (DCF)",
        "support": [("Present Value of Explicit Cash Flows", "present value of cash flows"), ("Present Value of Terminal Value", "present value of terminal value")],
        "params": lambda r: (lambda cf1: {"cf1": usd(cf1), "cf2": usd(int(cf1 * 1.1)), "cf3": usd(int(cf1 * 1.2)), "w": r.choice([8, 9, 10, 11, 12]), "g": r.choice([2, 2.5, 3])})(k(r, 40_000, 300_000, 5_000)),
        "questions": [
            "Calculate DCF valuation for cash flows {cf1}, {cf2}, {cf3} at {w}% WACC and {g}% terminal growth",
            "What is our enterprise value under DCF with projected cash flows {cf1}, {cf2}, {cf3}, {w}% discount rate, and {g}% terminal rate?",
            "Run a discounted cash flow valuation: cash flows {cf1}, {cf2}, {cf3} with {w}% cost of capital and {g}% perpetual growth."
        ],
        "meaning": {"any": "That represents the intrinsic value of future operating cash flows discounted to today."},
        "action": {
            "any": ["Use this valuation as an objective anchor when evaluating equity rounds or buyout offers.", "Focus capital on projects that out-earn that WACC hurdle rate to grow equity value."]
        },
    },
    {
        "sub": "DEFENSIVE_INTERVAL", "name": "your defensive survival horizon", "head": "Defensive Survival Horizon", "tier": "Buffer Assessment Tier",
        "support": [("Liquid Quick Assets", "quick assets"), ("Daily Operating Burn Rate", "daily operating expenses")],
        "params": lambda r: {"qa": usd(k(r, 40_000, 400_000, 5_000)), "burn": usd(k(r, 1_000, 10_000, 500))},
        "questions": [
            "Calculate defensive interval for quick assets {qa} and daily operating expenses {burn}",
            "What's our defensive interval ratio with liquid assets {qa} and daily burn {burn}?",
            "How many days can we survive on cash alone if quick assets are {qa} and daily expenses are {burn}?"
        ],
        "meaning": {
            "good": "Liquid assets provide a substantial defensive runway without relying on new sales.",
            "mid": "You have a moderate buffer, but an extended revenue freeze would test reserves.",
            "bad": "Liquid reserves cover only a narrow window; immediate inflows are essential."
        },
        "action": {
            "good": ["Maintain this liquid reserve buffer through your slow season."],
            "bad": ["Build liquid reserves or negotiate standby credit lines before a slow month hits."]
        },
    },
    {
        "sub": "ENTERPRISE_VALUE", "name": "your enterprise value", "head": "Enterprise Value (EV)",
        "support": [("Equity Value (Market Cap)", "equity value"), ("Net Debt", "net debt")],
        "params": lambda r: {"eq": usd(k(r, 100_000, 2_000_000, 25_000)), "d": usd(k(r, 20_000, 800_000, 10_000)), "c": usd(k(r, 10_000, 300_000, 5_000))},
        "questions": [
            "Calculate enterprise value for equity {eq}, total debt {d}, and cash {c}",
            "What is our enterprise value with equity value {eq}, debt {d}, and cash {c}?"
        ],
        "meaning": {"any": "Enterprise value reflects the total operational value of the business regardless of capital structure."},
        "action": {
            "any": ["Compare this valuation with recent industry multiples when considering acquisition or capital raises.", "Paying down high-cost debt shifts a larger share of enterprise value directly to equity holders."]
        },
    },
    {
        "sub": "CURRENCY_CONVERSION", "name": "the converted currency amount", "head": "Converted Amount",
        "support": [("Source Amount", "source amount"), ("Target Currency", "target currency")],
        "params": lambda r: {"amt": usd(k(r, 5_000, 200_000, 1_000)), "target": r.choice(["EUR", "GBP", "JPY", "CAD", "AUD"])},
        "questions": [
            "Convert {amt} to {target}",
            "What is {amt} in {target}?",
            "Calculate currency conversion of {amt} into {target}"
        ],
        "meaning": {"any": "The conversion reflects standard interbank spot pricing without bank markups."},
        "action": {
            "any": ["Lock in forward contracts if future vendor payments face currency volatility.", "Factor exchange fees into product pricing when purchasing foreign supplies."]
        },
    },
]

GOOD_TIER = re.compile(r"PRIME|HEALTHY|STRONG|EXCEPTIONAL|APPROVED|CONSERVATIVE|POSITIVE|RAPID|EFFICIENT|SELF_FUNDING|SAFE|LOW_BURDEN|NET_EXPANSION")
BAD_TIER = re.compile(r"ELEVATED|CRITICAL|DISTRESS|WEAK|DECLIN|HIGH_RISK|NEGATIVE|SEVERE|HIGH_BURDEN|SUBPRIME|AGGRESSIVE_LEVERAGE|DEFICIT|INSUFFICIENT|INADEQUATE|SLOW|CONTRACTION|BREACH|EXCESSIVE_LEVERAGE|STRETCHED|UNPROFITABLE|DESTRUCTION")
VALUE_TOKEN = re.compile(r"[+-]?[$€]?-?\d[\d,]*(?:\.\d+)?(?:%|x| units| months| days| years)?")


def parse_bullets(base: str) -> Dict[str, str]:
    fields = {}
    for label, value in re.findall(r"^(?:[-\d.]+\s*)?\*\*([^*]+)\*\*:\s*(.+)$", base, re.MULTILINE):
        fields[label.strip()] = value.replace("**", "").replace("`", "").strip()
    return fields


def figure(value: str) -> str:
    match = VALUE_TOKEN.match(value)
    return match.group(0) if match else value


def quant_reply(rng: random.Random, spec: Dict[str, Any], fields: Dict[str, str]) -> Optional[str]:
    if spec["head"] not in fields:
        return None
    head = figure(fields[spec["head"]]) + spec.get("unit", "")
    name = spec["name"]
    tier = fields.get(spec.get("tier", ""), "")
    tier = tier.split()[0] if tier else ""
    sentiment = "good" if GOOD_TIER.search(tier) else "bad" if BAD_TIER.search(tier) else "mid"
    cap = name[0].upper() + name[1:]
    first = rng.choice([
        f"{cap} comes out at {head}.",
        f"{cap} works out to {head}.",
        f"{cap} is {head} on the figures you gave.",
        f"{cap} lands at {head}.",
        f"{head} is {name} on these inputs.",
    ])
    supports = [(phrase, figure(fields[label])) for label, phrase in spec["support"] if label in fields]
    support = None
    if supports:
        parts = [f"{p} of {v}" for p, v in supports]
        joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        support = rng.choice([f"That rests on {joined}.", f"The inputs were {joined}.", f"This uses {joined}."])
    tier_s = rng.choice([f"The engine classifies this as {tier}.", f"That lands in the {tier} tier.", f"It is rated {tier}."]) if tier else None
    meanings = spec["meaning"]
    meaning = meanings.get(sentiment) or meanings.get("mid") or meanings.get("any") or meanings.get("bad")
    actions = spec["action"]
    action_pool = actions.get("any") or actions.get("good" if sentiment == "good" else "bad")
    return bold_first_figure(rng, finish(rng, first, [support, tier_s, meaning], rng.choice(action_pool)))


def build_quant_rows(rng: random.Random, per_spec: int) -> List[Dict[str, Any]]:
    rows = []
    for spec in QUANT_SPECS:
        made, attempts = 0, 0
        while made < per_spec and attempts < per_spec * 4:
            attempts += 1
            question = rng.choice(spec["questions"]).format(**spec["params"](rng))
            intent, sub, quant = route(question, False)
            if sub != spec["sub"] or not quant:
                continue
            captured: Dict[str, str] = {}

            def capture(base_reply: str, prompt_type: str = "diagnostic") -> str:
                captured.update(base=base_reply, prompt_type=prompt_type)
                return base_reply

            handler = next(s for s in SUBAGENTS if s.can_handle(sub))
            try:
                handler.handle_sub_intent(sub_intent=sub, request=AgentChatRequest(message=question), effective_csv=None, enrich_fn=capture)
            except Exception:
                continue
            if "base" not in captured:
                continue
            reply = quant_reply(rng, spec, parse_bullets(captured["base"]))
            if not reply:
                continue
            base = captured["base"]
            system = get_credit_underwriting_prompt(base) if captured["prompt_type"] == "underwriting" else get_cash_diagnostic_prompt(base)
            system = append_reference_cards(system, question)
            rows.append(make_row(system, question, reply, base, f"quant:{sub}"))
            made += 1
    return rows


VOLATILITY_QUESTIONS = [
    "What is our weekly revenue inflow volatility?",
    "Calculate our revenue inflow volatility CV from the statement.",
    "How volatile are our weekly customer receipts?",
    "What is our coefficient of variation on weekly inflows?",
    "Evaluate our revenue stability and inflow volatility tier.",
    "Are our customer inflows stable or irregular week over week?",
]


def build_revenue_volatility_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    rows = []
    profiles = list(PROFILES.keys())
    for _ in range(count):
        profile = rng.choice(profiles)
        days = rng.choice([45, 60, 75, 90])
        csv_data = make_statement(rng, profile, days=days)
        captured: Dict[str, str] = {}

        def capture(base_reply: str, prompt_type: str = "diagnostic") -> str:
            captured["base"] = base_reply
            return base_reply

        try:
            LiquiditySubagent.handle_sub_intent(
                "REVENUE_VOLATILITY",
                AgentChatRequest(message="What is our weekly revenue volatility?"),
                effective_csv=csv_data,
                enrich_fn=capture,
            )
        except Exception:
            continue
        if "base" not in captured:
            continue

        base = captured["base"]
        bullets = parse_bullets(base)
        cv = bullets.get("Weekly Revenue Inflow Volatility (CV)", "0.50")
        tier = bullets.get("Inflow Volatility Tier", "MODERATE")
        mean_w = bullets.get("Average Weekly Inflow", "$10,000.00")
        total_in = bullets.get("Total Customer Receipts", "$80,000.00")

        q = rng.choice(VOLATILITY_QUESTIONS)
        reply_options = [
            f"Your weekly revenue volatility comes out at a CV of {cv}, which lands in the {tier} volatility tier. Average weekly customer receipts sit at {mean_w} against total receipts of {total_in}. "
            + ("Inflows are steady and predictable, so cash forecasting carries low error." if tier == "LOW" else "Receipts fluctuate within normal commercial ranges, meaning a 60-day buffer is advisable." if tier == "MODERATE" else "Customer inflows are irregular and lumpy, creating cash pinch points between big payments.")
            + " "
            + ("Maintain your disciplined credit terms with existing clients." if tier == "LOW" else "Smooth out seasonal swings by securing a standby line of credit." if tier == "MODERATE" else "Incentivize clients to pay on milestone schedules or line up receivables financing."),
            f"The engine measures your weekly revenue volatility at {cv} ({tier} tier). Over the statement period, your business brought in {total_in} at an average pace of {mean_w} per week. "
            + ("This stable inflow velocity gives lenders high confidence in your cash debt-service capacity." if tier == "LOW" else "Weekly commercial receipts experience moderate swings, which is typical for growing SMEs." if tier == "MODERATE" else "Inflow lumpiness exposes operations to cash drag during receipt lulls.")
            + " "
            + ("Keep tracking weekly collection velocity to catch any drift early." if tier == "LOW" else "Align vendor payables with peak weekly inflow cycles to prevent overdrafts."),
        ]
        reply = bold_first_figure(rng, rng.choice(reply_options))
        system = append_reference_cards(get_cash_diagnostic_prompt(base), q)
        rows.append(make_row(system, q, reply, base, "diagnostic:volatility"))
    return rows


# ==============================================================================
# What-if cash scenarios (base_reply captured from the real LiquiditySubagent handler)
# ==============================================================================

SCENARIO_QUESTIONS = {
    "INVOICE_DELAY": [
        "What if {client} delays their {amt} invoice by {d} days?",
        "If {client} pays their {amt} bill {d} days late, do we go negative?",
        "Can our cash absorb a {d}-day delay on {client}'s {amt} invoice?",
    ],
    "COST_CUT": [
        "What if we cut costs by {amt} a month?",
        "How much runway do we gain if we reduce overhead by {amt} per month?",
        "If we trim {amt} of monthly spending, what happens to our runway?",
    ],
    "NEW_EXPENSE": [
        "How does our runway change if we hire someone at {amt} per month?",
        "What if we take on a new {amt} monthly lease?",
        "What happens if we add a new {amt} monthly software expense?",
    ],
    "REVENUE_DROP": [
        "What if our revenue drops {p}%?",
        "What if sales fall {p}% next quarter?",
        "How long does our cash last if revenue drops {p}%?",
    ],
}


def scenario_reply(rng: random.Random, kind: str, f: Dict[str, str], q: Dict[str, str]) -> Optional[str]:
    needed = ("Current Balance", "Baseline Daily Burn", "Scenario Daily Burn", "Baseline Runway", "Scenario Runway", "Scenario Deficit")
    if any(k not in f for k in needed):
        return None
    bb, sb = figure(f["Baseline Daily Burn"]) + "/day", figure(f["Scenario Daily Burn"]) + "/day"
    br, sr = f["Baseline Runway"], f["Scenario Runway"]
    positive = "Cash positive" in br
    if positive and "Cash positive" in sr:
        runway_s = "you stay cash positive, so runway is not under pressure"
    elif positive:
        runway_s = f"you go from cash positive to a {sr} runway"
    elif "Cash positive" in sr:
        runway_s = "you become cash positive"
    elif br == sr:
        runway_s = f"runway stays at {sr}"
    else:
        runway_s = f"runway moves from {br} to {sr}"

    bal = figure(f["Current Balance"])
    overdrawn = bal.startswith("$-")
    if positive and kind == "COST_CUT":
        return None  # no burn to cut: the reply would only restate $0.00/day
    if kind == "INVOICE_DELAY":
        if "Balance During Delay" not in f:
            return None
        if overdrawn:
            first = f"Your account is already overdrawn at {bal}, and the late {q['amt']} invoice from {q['client']} pushes it to {figure(f['Balance During Delay'])} until it is paid."
            effect = None
            action = rng.choice([
                f"Chase {q['client']} now and cut discretionary spending until the account is back above zero.",
                "Bring in overdue receivables first, and ask me to stage a short-term facility proposal if the gap stays open.",
            ])
        else:
            first = f"While {q['client']}'s {q['amt']} invoice is late, your balance sits at {figure(f['Balance During Delay'])} instead of {bal}."
        if overdrawn:
            pass
        elif not positive and sr != br:
            effect = f"That reduced balance only lasts {sr}, so the {q['d']}-day delay would run you out of cash before the payment lands."
            action = rng.choice([
                f"Chase {q['client']} now, and ask me to stage a short-term facility proposal if the payment slips.",
                "Hold back discretionary payments until the invoice clears, and line up a short facility as a backstop.",
            ])
        else:
            effect = (f"Your {br.replace(' days', '-day')} runway still holds, because the reduced balance outlasts the {q['d']}-day delay." if not positive
                      else f"Inflows still exceed outflows, so the {q['d']}-day delay thins the cushion without a runway problem.")
            action = rng.choice([
                f"Still follow up with {q['client']} so one late payment does not become a habit.",
                "Keep the delay on your watch list and recheck once the payment lands.",
            ])
    else:
        lead = {
            "COST_CUT": f"Cutting {q['amt']} a month takes burn from {bb} to {sb}",
            "NEW_EXPENSE": f"Adding that {q['amt']} monthly cost lifts burn from {bb} to {sb}",
            "REVENUE_DROP": f"A {q['p']}% drop in revenue lifts burn from {bb} to {sb}",
        }[kind]
        change = {"NEW_EXPENSE": f"that {q['amt']} monthly cost", "REVENUE_DROP": f"a {q['p']}% revenue drop"}.get(kind, "")
        if overdrawn:
            if kind != "COST_CUT":
                tail = "which deepens the overdraft faster"
            elif sb == "$0.00/day":
                tail = "which stops the slide, though the account stays overdrawn"
            else:
                tail = "which slows the slide but does not clear the overdraft"
            first = f"Your account is already overdrawn at {bal}. {lead}, {tail}."
        elif positive and "Cash positive" in sr:
            first = f"Even with {change}, inflows still exceed outflows, so you stay cash positive."
            return " ".join((first, "No deficit appears in the forecast window.", "Recheck once it starts, since a thinner margin leaves less room for a slow month."))
        elif positive:
            first = f"{change[0].upper() + change[1:]} turns a cash-positive position into a {sb} burn, giving you a {sr.replace(' days', '-day')} runway."
        else:
            first = f"{lead}, and {runway_s}."
        effect = None
        if "Runway Change" in f and not overdrawn and f["Runway Change"] != "+0 days":
            effect = rng.choice([f"That is a change of {f['Runway Change']} against today's statement.", f"The net effect is {f['Runway Change']} of runway."])
        if kind == "COST_CUT":
            action = rng.choice([
                "Name the specific costs that go, then recheck runway on your next statement.",
                "Make the cut on recurring items such as subscriptions or contractors so it holds month after month.",
            ])
        else:
            action = rng.choice([
                "Line up collections or a short facility before committing, so the gap does not catch you.",
                "Decide which costs you would cut first if this happens, before you need to.",
            ])

    deficit = f["Scenario Deficit"]
    m = re.match(r"(\$[\d,]+\.\d{2}) shortfall on (\d{4}-\d{2}-\d{2})", deficit)
    deficit_s = f"The forecast then shows a {m.group(1)} shortfall on {m.group(2)}." if m else "No deficit appears in the forecast window."
    return bold_first_figure(rng, " ".join(s for s in (first, effect, deficit_s, action) if s))


def build_scenario_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    rows = []
    attempts = 0
    while len(rows) < count and attempts < count * 4:
        attempts += 1
        kind = rng.choice(list(SCENARIO_QUESTIONS))
        csv = make_statement(rng, rng.choices(list(PROFILES), weights=PROFILE_WEIGHTS)[0])
        q = {"client": rng.choice(CLIENT_NAMES), "amt": usd(k(rng, 2_000, 60_000, 500)), "d": str(rng.choice([7, 10, 14, 21, 30, 45])), "p": str(rng.choice([5, 10, 15, 20, 25, 30, 40]))}
        question = rng.choice(SCENARIO_QUESTIONS[kind]).format(**q)
        if route(question, True)[1] != "CASH_SCENARIO":
            continue
        captured: Dict[str, str] = {}

        def capture(base_reply: str, prompt_type: str = "diagnostic", **_: Any) -> str:
            captured["base"] = base_reply
            return base_reply

        LiquiditySubagent.handle_sub_intent("CASH_SCENARIO", AgentChatRequest(message=question), csv, capture)
        base = captured.get("base")
        if not base:
            continue
        fields = parse_bullets(base)
        # Synthetic long statements end overdrawn about half the time; keep what-ifs mostly solvent.
        if figure(fields.get("Current Balance", "")).startswith("$-") and rng.random() < 0.7:
            continue
        reply = scenario_reply(rng, kind, fields, q)
        if not reply:
            continue
        system = append_reference_cards(get_cash_diagnostic_prompt(base), question)
        rows.append(make_row(system, question, reply, base, f"scenario:{kind}"))
    return rows


# ==============================================================================
# Bridge financing plans (question mode only: rows never stage or claim staging)
# ==============================================================================

BRIDGE_QUESTIONS = [
    "How should we cover the projected shortfall?",
    "What is the cheapest way to bridge our cash gap?",
    "How do we fund the deficit before it hits?",
    "What's the cheapest mix of financing to cover the shortfall?",
    "How can we cover the shortfall cheaply?",
    "Which financing should we use to cover the projected deficit?",
]
BRIDGE_STEP = re.compile(r"(\$[\d,]+\.\d{2}) at ([\d.]+%) APR for (\d+) days \(cost (\$[\d,]+\.\d{2})\)")


def bridge_reply(rng: random.Random, f: Dict[str, str]) -> Optional[str]:
    if f.get("Projected Shortfall", "").startswith("None"):
        return rng.choice([
            "No shortfall is projected within the forecast horizon, so the bridge target is $0.00 and there is nothing to bridge right now. Recheck after your next statement or before any large new commitment.",
            "Your forecast shows no deficit, so the bridge target is $0.00 and no financing is needed today. Keep the buffer you have and rerun this if a big payment or hire is coming.",
        ])
    m = re.match(r"(\$[\d,]+\.\d{2}) on (\d{4}-\d{2}-\d{2})", f.get("Projected Shortfall", ""))
    if not m or "Bridge Target" not in f:
        return None
    parts = [f"Your forecast shows a {m.group(1)} shortfall on {m.group(2)}, so the plan targets {figure(f['Bridge Target'])} including a {figure(f.get('Cash Buffer', '$0.00'))} cash buffer."]
    steps = [(label.split(": ", 1)[1], value) for label, value in f.items() if label.startswith("Step ")]
    for i, (name, value) in enumerate(steps):
        s = BRIDGE_STEP.match(value)
        if not s:
            return None
        amt, apr, days, cost = s.groups()
        lead = "Start by" if i == 0 else "Then"
        if "supplier agreement" in value:
            parts.append(f"{lead} {'deferring' if i == 0 else 'defer'} {amt} of supplier payments for {days} days, which costs nothing but needs their agreement.")
        elif "Line" in name or "Credit" in name:
            parts.append(f"{lead} {'drawing' if i == 0 else 'draw'} {amt} on the {name} at {apr} APR, about {cost} over {days} days.")
        else:
            parts.append(f"{lead} {'factoring' if i == 0 else 'factor'} {amt} of open invoices through the {name} at {apr} APR, about {cost} over {days} days.")
    uncovered = figure(f.get("Uncovered Gap", "$0.00"))
    if uncovered != "$0.00":
        parts.append(f"That still leaves {uncovered} uncovered, which points to a structural gap rather than a timing problem.")
    else:
        parts.append(f"The total estimated cost is {figure(f.get('Total Estimated Cost', '$0.00'))}.")
    if any("supplier agreement" not in v for _, v in steps):
        parts.append(rng.choice([
            "Ask me to prepare the plan and I will draft the financing requests for you to review and send.",
            "If it looks right, ask me to prepare it and the financing requests will be ready for you to send.",
        ]))
    else:
        parts.append("Agree the deferral with your suppliers before that date; no financing needs staging.")
    return bold_first_figure(rng, " ".join(parts))


def build_bridge_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    rows = []
    attempts = 0
    while len(rows) < count and attempts < count * 4:
        attempts += 1
        question = rng.choice(BRIDGE_QUESTIONS)
        if route(question, True)[1] != "BRIDGE_PLAN":
            continue
        profile = rng.choices(["slow_burn", "fast_burn", "near_deficit", "cash_positive"], weights=[6, 3, 2, 1])[0]
        csv = make_statement(rng, profile)
        captured: Dict[str, str] = {}

        def capture(base_reply: str, prompt_type: str = "diagnostic", **_: Any) -> str:
            captured["base"] = base_reply
            return base_reply

        LiquiditySubagent.handle_sub_intent("BRIDGE_PLAN", AgentChatRequest(message=question), csv, capture)
        base = captured.get("base")
        reply = bridge_reply(rng, parse_bullets(base)) if base else None
        if not reply:
            continue
        system = append_reference_cards(get_cash_diagnostic_prompt(base), question)
        rows.append(make_row(system, question, reply, base, "bridge:plan"))
    return rows


# ==============================================================================
# Outflow Category Breakdown rows
# ==============================================================================

OUTFLOW_QUESTIONS = [
    "Which outflows drive our burn?",
    "Can you break down our operating outflows?",
    "Give me an outflow breakdown by category.",
    "Which categories are driving our cash outflows?",
    "Break down our cash outflows",
    "Categorize our operating outflows",
    "What is our outflow breakdown?",
    "Show me the outflow breakdown by category",
    "Audit our outflow breakdown",
]


def outflow_breakdown_reply(rng: random.Random, f: Dict[str, str]) -> Optional[str]:
    gross = figure(f.get("Gross Outflows", ""))
    daily = figure(f.get("Average Daily Outflow", ""))
    driver_val = f.get("Primary Cost Driver", "")
    if not gross or not daily or not driver_val:
        return None

    driver_match = re.match(r"([A-Za-z\s\&]+)\s*\(([\$[\d,]+\.\d{2}),\s*([\d.]+%)[^)]*\)", driver_val)
    if not driver_match:
        return None
    name, amt, pct = driver_match.groups()
    cat_name = name.strip()

    parts = [
        f"Across this reviewed period your gross operating outflows totaled {gross}, averaging {daily}/day.",
        f"Your primary cost driver is {cat_name} at {amt} ({pct} of total spending).",
    ]

    parts.append(rng.choice([
        f"Audit discretionary vendors in {cat_name} to extend your cash runway.",
        f"Review terms on {cat_name} commitments to protect operating cash buffers.",
        f"Control {cat_name} expenditures before scaling additional operating overhead.",
    ]))
    return bold_first_figure(rng, " ".join(parts))


def build_outflow_breakdown_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    rows = []
    attempts = 0
    while len(rows) < count and attempts < count * 4:
        attempts += 1
        question = rng.choice(OUTFLOW_QUESTIONS)
        if route(question, True)[1] != "OUTFLOW_BREAKDOWN":
            continue
        profile = rng.choices(["slow_burn", "fast_burn", "near_deficit", "cash_positive"], weights=[4, 4, 2, 2])[0]
        csv = make_statement(rng, profile)
        captured: Dict[str, str] = {}

        def capture(base_reply: str, prompt_type: str = "diagnostic", **_: Any) -> str:
            captured["base"] = base_reply
            return base_reply

        LiquiditySubagent.handle_sub_intent("OUTFLOW_BREAKDOWN", AgentChatRequest(message=question), csv, capture)
        base = captured.get("base")
        if not base:
            continue
        reply = outflow_breakdown_reply(rng, parse_bullets(base))
        if not reply:
            continue
        system = append_reference_cards(get_cash_diagnostic_prompt(base), question)
        rows.append(make_row(system, question, reply, base, "outflow:breakdown"))
    return rows


# ==============================================================================
# Accounts Receivable Ageing rows
# ==============================================================================

RECEIVABLES_AGEING_QUESTIONS = [
    "Who owes us and how late are they?",
    "Audit our accounts receivable ageing",
    "Which customers have overdue invoices?",
    "Show our accounts receivable aging schedule",
    "Audit receivables ageing schedule",
    "Give me an accounts receivable breakdown by age",
]


def make_ar_csv(rng: random.Random, as_of: date) -> str:
    customers = [
        "Acme Corp", "Wayne Enterprises", "Stark Industries", "Globex",
        "Initech", "Umbrella Corp", "Cyberdyne Systems", "Hooli", "Pied Piper",
    ]
    lines = ["invoice_id,customer_name,issue_date,due_date,amount,status"]
    count = rng.randint(4, 5)
    for i in range(1, count + 1):
        inv_id = f"INV-20{i:02d}"
        cust = rng.choice(customers)
        amt = rng.randint(3, 40) * 1000
        due_offset = rng.choice([-75, -45, -20, -5, 15, 30])
        due_dt = as_of + timedelta(days=due_offset)
        issue_dt = due_dt - timedelta(days=30)
        lines.append(f"{inv_id},{cust},{issue_dt.isoformat()},{due_dt.isoformat()},{amt:.2f},UNPAID")
    return "\n".join(lines)


def receivables_ageing_reply(rng: random.Random, f: Dict[str, str]) -> Optional[str]:
    total_ar = figure(f.get("Total Outstanding AR", ""))
    total_overdue = figure(f.get("Total Overdue", ""))
    overdue_match = re.search(r"\(([\d.]+%\s*of\s*AR)\)", f.get("Total Overdue", ""))
    overdue_pct = overdue_match.group(1) if overdue_match else "past due"
    top_conc = f.get("Top Debtor Concentration", "")
    risk_posture = f.get("Receivables Risk Posture", "")
    risk_tier = risk_posture.split(" — ")[0].strip() if " — " in risk_posture else "EVALUATED"

    if not total_ar or not total_overdue:
        return None

    parts = [
        f"Your total outstanding receivables stand at {total_ar}, with {total_overdue} past due ({overdue_pct}, {risk_tier} risk).",
    ]
    for b_key in ("90+ Days Past Due", "61-90 Days Past Due", "31-60 Days Past Due", "1-30 Days Past Due"):
        val = f.get(b_key)
        if val and not val.startswith("$0.00"):
            b_match = re.search(r"(\$[\d,]+\.\d{2})\s*\(([\d.]+%)", val)
            if b_match:
                parts.append(f"Delinquency is led by {b_match.group(1)} in the {b_key} bucket ({b_match.group(2)}).")
                break

    if top_conc and top_conc != "0.00%":
        parts.append(f"Debtor concentration shows your largest customer represents {top_conc} of open receivables.")

    parts.append(rng.choice([
        "Prioritize immediate collection follow-up on delinquent accounts before exploring bridge financing.",
        "Accelerate collections on overdue accounts to protect operating cash buffers.",
        "Consider factoring eligible open invoices to convert receivables into immediate working capital.",
    ]))
    return bold_first_figure(rng, " ".join(parts))


def build_receivables_ageing_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    rows = []
    attempts = 0
    while len(rows) < count and attempts < count * 4:
        attempts += 1
        base_q = rng.choice(RECEIVABLES_AGEING_QUESTIONS)
        if route(base_q, False)[1] != "RECEIVABLES_AGEING":
            continue
        as_of = date(2026, rng.choice([8, 9, 10]), rng.randint(1, 28))
        ar_csv = make_ar_csv(rng, as_of)
        question = f"{base_q} as of {as_of.isoformat()}:\n{ar_csv}"

        captured: Dict[str, str] = {}

        def capture(base_reply: str, prompt_type: str = "diagnostic", **_: Any) -> str:
            captured["base"] = base_reply
            return base_reply

        LiquiditySubagent.handle_sub_intent("RECEIVABLES_AGEING", AgentChatRequest(message=question), None, capture)
        base = captured.get("base")
        if not base:
            continue
        reply = receivables_ageing_reply(rng, parse_bullets(base))
        if not reply:
            continue
        system = append_reference_cards(get_cash_diagnostic_prompt(base), base_q, k=1)
        rows.append(make_row(system, question, reply, base, "receivables:ageing"))
    return rows



# ==============================================================================
# Conversational and missing-statement rows
# ==============================================================================

CONVERSATION = {
    "greeting": {
        "questions": ["hi", "hello", "hey", "good morning", "hi there", "hey copilot", "good afternoon", "hello there", "morning", "hiya"],
        "no_statement": [
            "I'm the Autonomous SME Finance Copilot, your AI CFO for cash runway, burn rate, overdraft forecasting and credit matching. Upload your bank statement CSV and I will run a full liquidity diagnosis.",
            "Good to meet you; I'm the Autonomous SME Finance Copilot. Drop your bank statement CSV into the upload area so I can calculate your runway and flag any cash gaps.",
            "Welcome. I'm the Autonomous SME Finance Copilot, built to audit cash flow and working capital for small businesses. Share your bank statement CSV to get started.",
            "This is the Autonomous SME Finance Copilot, ready to look at your cash position. Upload a bank statement CSV and I will work out your runway, burn and borrowing capacity.",
        ],
        "statement_loaded": [
            "Your statement is loaded and ready. Ask me about runway, daily burn, upcoming shortfalls or what credit you qualify for.",
            "Good to see you. With your statement already loaded, I can check runway, burn rate, deficit risk or financing options; just ask.",
            "Welcome back. Your bank statement is in session, so pick a question: cash runway, burn, overdraft risk or borrowing capacity.",
        ],
    },
    "capabilities": {
        "questions": ["what can you do?", "who are you?", "what do you do", "tell me about yourself", "what are you capable of?", "what can you help me with?", "what is this app?", "introduce yourself"],
        "no_statement": [
            "I'm the Autonomous SME Finance Copilot: I audit cash runway, forecast overdrafts, review working capital and match you with non-predatory credit. Upload your bank statement CSV and I will start with a liquidity diagnosis.",
            "I act as a fractional CFO for small businesses, covering runway, burn rate, deficit early warnings and financing options. Share your bank statement CSV so I can work from your real numbers.",
            "I'm the Autonomous SME Finance Copilot, focused on cash flow, working capital and credit underwriting for SMEs. Upload a bank statement CSV to see where your cash stands.",
        ],
        "statement_loaded": [
            "I audit cash runway, forecast shortfalls, review working capital and match you with non-predatory credit. Your statement is already loaded, so ask about any of those and I will answer from your numbers.",
            "Think of me as a fractional CFO: runway, burn, deficit warnings and financing. Your statement is loaded, so a good first question is how long your cash will last.",
        ],
    },
    "how_to_start": {
        "questions": ["how does this work?", "how do I get started?", "where do I start?", "how do I use this?", "what should I do first?", "how do I begin?", "walk me through how this works"],
        "no_statement": [
            "First, upload your bank statement CSV or paste the transactions. The engine then computes your Daily Average Balance, burn velocity, runway and any deficit warning, and any proposal it drafts waits for your explicit approval. Upload your statement to begin.",
            "Start by uploading a bank statement CSV in the dropzone. I run a deterministic liquidity audit on it, then stage any recommended action for your review and approval. Go ahead and upload when ready.",
            "It works in three steps: upload your statement, get an instant liquidity audit, then review any staged proposals before anything executes. Upload your bank statement CSV to start.",
        ],
        "statement_loaded": [
            "Your statement is already loaded, so you can skip straight to questions. Ask about runway, burn, deficits or financing, and any action I propose is staged for your approval first.",
            "You are past the first step since the statement is loaded. Ask me how long your cash lasts or what you can borrow, and I will answer from the verified numbers.",
        ],
    },
    "thanks": {
        "questions": ["thanks", "thank you", "thanks, that helps", "great, thanks", "cheers", "ok thanks", "perfect, thank you"],
        "no_statement": [
            "Glad to help. When you're ready, upload your bank statement CSV and I will run the full cash diagnosis.",
            "Anytime. Upload a bank statement CSV whenever you want me to look at your runway and burn.",
        ],
        "statement_loaded": [
            "Glad that helped. Ask whenever you want to look at runway, deficits or financing again.",
            "Anytime. Your statement stays loaded, so follow-up questions on cash or credit are quick.",
            "You're welcome. If anything changes, upload a fresh statement and I will rerun the numbers.",
        ],
    },
    "privacy": {
        "questions": ["is my data safe?", "do you store my bank data?", "who can see my statement?", "can you move money from my account?"],
        "no_statement": [
            "Calculations run on deterministic rules, and I never move money or contact lenders: I draft requests and you send them. Upload your bank statement CSV when you're comfortable and I will start the analysis.",
            "I only draft actions; anything that moves money is a request you send yourself. When you're ready, upload a bank statement CSV to begin.",
        ],
        "statement_loaded": [
            "Your statement is used for the analysis in this session, and I never move money: anything financial is a request you send yourself. Ask me about runway or financing whenever you're ready.",
            "I can draft proposals, but I never send or execute them; you do. With the statement loaded, ask any cash or credit question.",
        ],
    },
}
SPANISH = [
    ("hola", "Soy el Autonomous SME Finance Copilot, tu CFO digital para flujo de caja y crédito. Sube el CSV de tu extracto bancario y calcularé tu runway y riesgos de liquidez."),
    ("hola, ¿qué puedes hacer?", "Soy el Autonomous SME Finance Copilot: analizo tu runway de caja, el ritmo de gasto, riesgos de sobregiro y opciones de crédito no abusivas. Sube el CSV de tu extracto bancario para empezar."),
    ("buenos días", "Soy el Autonomous SME Finance Copilot. Comparte el CSV de tu extracto bancario y revisaré tu posición de caja."),
]
MISSING_STATEMENT = {
    "diagnostic": {
        "questions": ["How long will my cash last?", "What's our burn rate?", "What is our cash balance?", "Are we heading for a cash shortfall?", "How many days of runway do we have left?", "What's the daily burn rate?", "Will we have a cash shortfall?"],
        "replies": [
            "No bank statement CSV is loaded in this session yet, so there are no figures to work from. Upload your recent bank statement CSV, ideally covering the last three months, and I will calculate your Daily Average Balance, net burn and runway.",
            "There is no statement loaded right now, so I can't compute that yet. Upload your bank statement CSV and I will work out your DAB, burn rate and cash runway from it.",
            "I don't have a bank statement for this session yet. Share your transaction CSV, ideally the last three months, and I will answer with your exact runway and burn.",
            "To audit your cash runway and daily burn rate, please upload your recent bank statement CSV. I will immediately analyze your transaction inflows and outflows.",
            "Please provide a bank statement CSV to begin the liquidity diagnosis. Once loaded, I will report your liquid balance, net burn, and projected runway.",
            "I require transaction data to evaluate your cash position. Upload your company's bank statement CSV and I will verify your runway and recurring expenditure.",
            "There is no transaction data loaded in this session. Upload your bank statement CSV so I can extract your cash flows and determine your runway.",
            "A bank statement CSV is required to compute your cash runway and burn metrics. Share your transaction file to view an exact liquidity breakdown.",
        ],
    },
    "underwriting": {
        "questions": ["Can we qualify for a loan?", "How much can we borrow?", "What financing options do we have?", "What credit line can we get?", "Can I get a business loan?", "Are we eligible for financing?"],
        "replies": [
            "No bank statement CSV is loaded yet, so I can't assess borrowing capacity. Upload your recent bank statement CSV and I will evaluate your Daily Average Balance and inflow volatility to match facilities with true APR disclosures.",
            "There is no statement in this session yet, which underwriting needs. Upload your bank statement CSV, ideally the last three months, and I will size your qualified limit and show matching facilities.",
            "I need your transaction history before I can underwrite. Share your bank statement CSV and I will work out your DAB, risk tier and non-predatory financing options.",
            "Please upload your company bank statement CSV to evaluate borrowing eligibility. I will calculate your Daily Average Balance and screen matching facilities against predatory rates.",
            "To determine qualified financing limits, upload a recent bank statement CSV. I will assess your inflow volatility and present pre-qualified options with true APRs.",
            "Credit underwriting requires your recent bank transactions. Upload your bank statement CSV so I can establish your risk tier and maximum credit limit.",
            "I cannot assess your credit line without transaction records. Share your bank statement CSV to see your qualified borrowing capacity and matched facilities.",
            "Upload your business bank statement CSV to initiate digital underwriting. I will evaluate your cash consistency and match suitable working capital options.",
        ],
    },
}


def build_conversational_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    rows = []
    base_prompt = get_conversational_system_prompt()
    pool = []
    for category, spec in CONVERSATION.items():
        for question in spec["questions"]:
            for loaded in (False, True):
                intent, _, quant = route(question, loaded)
                if intent == "GENERAL_ASSISTANCE" and not quant:
                    pool.append((category, question, loaded))
    for _ in range(count):
        category, question, loaded = rng.choice(pool)
        reply = rng.choice(CONVERSATION[category]["statement_loaded" if loaded else "no_statement"])
        system = base_prompt + (STATEMENT_LOADED_NOTE if loaded else NO_STATEMENT_DIRECTIVE)
        rows.append(make_row(system, question, reply, "", f"chat:{category}:{'loaded' if loaded else 'none'}"))
    for question, reply in SPANISH:
        if route(question, False)[0] == "GENERAL_ASSISTANCE":
            for _ in range(4):
                rows.append(make_row(base_prompt + NO_STATEMENT_DIRECTIVE, question, reply, "", "chat:spanish:none"))
    return rows


def build_missing_statement_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    rows = []
    wanted = {"diagnostic": "CASH_DIAGNOSTIC", "underwriting": "CREDIT_UNDERWRITING"}
    pool = [
        (context, q)
        for context, spec in MISSING_STATEMENT.items()
        for q in spec["questions"]
        if route(q, False)[0] == wanted[context] and not route(q, False)[2]
    ]
    for _ in range(count):
        context, question = rng.choice(pool)
        reply = rng.choice(MISSING_STATEMENT[context]["replies"])
        rows.append(make_row(get_missing_statement_prompt(context), question, reply, "", f"missing:{context}"))
    return rows


# ==============================================================================
# Overhauled Concept rows with non-verbatim synthesis and qualitative SME examples
# ==============================================================================

SME_CONTEXTS = [
    "a regional wholesale distributor balancing 60-day customer receivables with weekly supplier deliveries",
    "a commercial electrical contractor managing progress billing milestones and payroll obligations",
    "an independent medical clinic balancing equipment lease obligations and monthly payer reimbursements",
    "a commercial bakery managing seasonal holiday ingredient inventory and wholesale restaurant accounts",
    "a light manufacturing shop managing raw materials inventory and machinery maintenance expenses",
    "an omnichannel retail apparel brand managing inventory turnover and seasonal merchant receivables",
    "a B2B software consultancy managing monthly client retainers and project milestone billings",
    "a specialized logistics carrier managing fleet fuel costs, vehicle leases, and shipper payment terms",
]


def build_concept_card_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    cards = load_cards()
    if not cards:
        return []

    base_concept_prompt = get_concept_prompt()
    pool = []

    for card in cards:
        lines = card.text.splitlines()
        sections = {}
        for line in lines:
            m = re.match(r"\*\*(.+?):\*\*\s*(.*)", line.strip())
            if m:
                sections[m.group(1).lower()] = m.group(2).strip()

        what = sections.get("what it is", "")
        why = sections.get("why it matters", "")
        health = sections.get("healthy vs warning", "")
        todo = sections.get("what to do", "")

        if not (what and why):
            continue

        title_clean = re.sub(r"\s*\(.*?\)", "", card.title).strip()
        acronym_match = re.search(r"\((.*?)\)", card.title)
        acronym = acronym_match.group(1).strip() if acronym_match else ""

        # Diverse, natural questions tailored to card domain (no templated "What is a healthy X" glitches)
        title_l = title_clean.lower()
        is_gov = card.area == "app_safety" or any(w in title_l for w in ("tier", "gate", "owner", "math", "blockchain", "privacy", "double-financing"))
        is_metric = any(w in title_l for w in ("ratio", "dscr", "fccr", "score", "margin", "roic", "roa", "eva", "wacc", "turnover", "coverage"))
        is_cash = any(w in title_l for w in ("balance", "runway", "burn", "dab", "cycle", "overdraft", "deficit", "drag", "dso", "dpo", "dio", "wcr"))
        is_fac = any(w in title_l for w in ("factoring", "line of credit", "mca", "merchant", "leasing", "trade credit", "financing"))
        is_strat = card.area == "marketing_strategy" or any(w in title_l for w in ("cac", "ltv", "retention", "nrr", "leverage", "pricing", "sensitivity"))

        questions = [f"What is {card.title}?"]
        if is_gov:
            questions.extend([
                f"How does {title_clean} protect our business bank accounts?",
                f"Can you explain the rules around {title_clean} in this copilot?",
                f"Why is {title_clean} required before any money moves?",
                f"What is the difference between staged proposals and {title_clean}?",
            ])
        elif is_metric:
            questions.extend([
                f"Why does {title_clean} matter when applying for commercial credit?",
                f"What is considered a safe benchmark for {title_clean}?",
                f"How do underwriters evaluate {title_clean} on our financial statements?",
                f"What steps can we take to improve our {title_clean}?",
            ])
            if acronym:
                questions.extend([
                    f"What does {acronym} mean in business banking?",
                    f"How do commercial lenders judge our {acronym}?",
                ])
        elif is_cash:
            questions.extend([
                f"Why is {title_clean} a critical indicator of small business liquidity?",
                f"How does {title_clean} affect our day-to-day operations?",
                f"What should we do if our {title_clean} starts deteriorating?",
                f"Can you explain {title_clean} in plain English for our management team?",
            ])
        elif is_fac:
            questions.extend([
                f"How does {title_clean} work for an SME and what is the true cost?",
                f"When is it better to use {title_clean} instead of a bank credit line?",
                f"What are the pros and cons of {title_clean} for working capital?",
                f"Is {title_clean} considered non-predatory financing?",
            ])
        elif is_strat:
            questions.extend([
                f"How does {title_clean} impact our monthly profitability and cash runway?",
                f"Why is {title_clean} vital when scaling an SME?",
                f"What should leadership do if our {title_clean} falls below industry standards?",
                f"Explain how {title_clean} connects to our working capital cycle.",
            ])
        else:
            questions.extend([
                f"Why does {title_clean} matter for our company finances?",
                f"How should an SME owner evaluate {title_clean}?",
                f"What operational actions should we take regarding {title_clean}?",
            ])

        system = format_reference_cards(base_concept_prompt, [card])

        # Generate original, non-verbatim synthesized explanations with concrete SME operational examples
        replies = []

        # Grounded benchmark figures from the card if available
        threshold_note = ""
        if health:
            # Extract key benchmarks from health section
            benchmarks = re.findall(r"\b\d+(?:\.\d+)?(?:x|%| days| months| years)?\b", health)
            if benchmarks:
                threshold_note = f" In commercial underwriting, key reference benchmarks include {', '.join(benchmarks[:3])}."
            else:
                threshold_note = " Monitoring this metric against historical patterns helps catch liquidity pressure before it disrupts operations."

        sme_context = rng.choice(SME_CONTEXTS)
        action_note = f" {todo}" if todo and len(todo) < 120 else " Review this area on your regular financial statements to maintain proactive liquidity management."

        rep1 = (
            f"{title_clean} provides a vital perspective on enterprise liquidity and financial stability. "
            f"For {sme_context}, keeping a firm grasp on this area ensures that operational cash flow remains adequate to meet upcoming obligations."
            f"{threshold_note}"
            f"{action_note}"
        )
        rep2 = (
            f"In small business finance, {title_clean.lower()} directly reflects how effectively capital is deployed and protected. "
            f"When an enterprise such as {sme_context} monitors this indicator, it can preemptively address cash traps and manage working capital efficiently."
            f"{threshold_note}"
            f" Regularly audit your operational ledgers and consult verified statements to keep this posture strong."
        )

        for rep in (rep1, rep2):
            cleaned = sanitize_cfo_reply(rep.strip())
            overlap = compute_ngram_overlap(cleaned, card.text, n=4)
            if overlap < 0.35 and len(cleaned) > 50:
                for q in questions:
                    pool.append((system, q, cleaned, card.area))

    if not pool:
        return []

    rng.shuffle(pool)
    rows = []
    for _ in range(count):
        system, q, reply, area = rng.choice(pool)
        rows.append(make_row(system, q, reply, "", f"concept:{area}"))
    return rows


# ==============================================================================
# Multi-turn conversational rows (~10% of dataset)
# ==============================================================================

CLIENT_NAMES = ["Apex Logistics", "Cascade Construction", "Delta Manufacturing", "Evergreen Retail", "Falcon Distribution", "Horizon Tech", "Pinnacle Services", "Summit Media", "Vanguard Industrial"]
SUPPLIER_NAMES = ["National Steel", "Pacific Packaging", "Precision Parts", "Global Ingredients", "Standard Supply", "Metro Wholesalers", "Allied Materials", "Direct Paper"]


def build_multiturn_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    rows = []
    attempts = 0
    max_attempts = count * 3

    while len(rows) < count and attempts < max_attempts:
        attempts += 1
        scenario = rng.choice([
            "runway_whatif",
            "underwriting_governance",
            "trade_credit",
            "burn_rate",
            "deficit_action",
            "break_even_pricing",
            "dscr_headroom",
            "dupont_leverage",
            "altman_turnaround",
            "receivables_collection",
            "outflow_cost_cut",
            "bridge_staging",
        ])

        # Follow-up answers quote only figures already in the conversation or in engine output placed in the
        # system prompt; numbers_are_grounded drops any row where the reply would need arithmetic of its own.
        if scenario == "runway_whatif":
            csv = make_statement(rng, rng.choices(list(PROFILES), weights=PROFILE_WEIGHTS)[0], days=rng.choice([30, 45]))
            cash = tool_analyze_cash_flow(csv)
            t1_base = cash_base_reply(cash, "RUNWAY")
            t1_q = rng.choice(CASH_QUESTIONS["RUNWAY"])
            t1_a = cash_reply(rng, cash, "RUNWAY")
            if not t1_a:
                continue

            client = rng.choice(CLIENT_NAMES)
            inv = money(rng.randrange(8000, 75000, 2500))
            delay = rng.choice([10, 14, 21, 30, 45])
            bal, burn, days = money(cash["current_balance"]), money(cash["average_daily_burn"]), cash["runway_days"]
            if Decimal(cash["current_balance"]) <= 0:
                outlook = (
                    f"Your account is already overdrawn at {bal}, so a {delay}-day slip on {client}'s {inv} invoice "
                    "extends the time you spend below zero."
                )
            elif days is None:
                outlook = (
                    f"Your inflows currently exceed outflows, so a {delay}-day slip on {client}'s {inv} invoice thins your cushion "
                    f"without pushing the {bal} balance into a runway problem."
                )
            elif days < delay:
                outlook = (
                    f"That is a real risk: your runway is {days} days, shorter than the {delay}-day delay, "
                    f"so the {bal} balance could run out before {client}'s {inv} arrives."
                )
            else:
                outlook = (
                    f"Your {days}-day runway outlasts the {delay}-day delay, but for those days you carry {burn}/day of burn "
                    f"without the {inv} you planned on from {client}."
                )
            t2_q, t2_a = rng.choice([
                (f"What if {client} delays their {inv} invoice by {delay} days?",
                 f"{outlook} Chase the invoice now and hold back discretionary payments until it clears."),
                (f"If {client} pays their {inv} bill {delay} days late, do we face a deficit?",
                 f"{outlook} If the payment slips further, ask me to stage a short-term credit line proposal for your review."),
                (f"How does a {delay}-day payment delay from {client} on {inv} affect our runway?",
                 f"{outlook} Your runway figure assumes customer receipts keep arriving on their usual schedule, so treat it as optimistic until {client} pays."),
            ])
            sys_prompt = append_reference_cards(get_cash_diagnostic_prompt(t1_base), t1_q, k=1)
            history = [{"role": "user", "content": t1_q}, {"role": "assistant", "content": t1_a}]
            rows.append(make_multiturn_row(sys_prompt, history, t2_q, t2_a, "", "multiturn:runway_whatif"))

        elif scenario == "underwriting_governance":
            csv = make_statement(rng, rng.choices(list(PROFILES), weights=PROFILE_WEIGHTS)[0], days=rng.choice([30, 45]))
            uw = tool_underwrite_credit(csv, nsf_count=rng.choice([0, 1]))
            t1_base = underwriting_base_reply(uw)
            t1_q = rng.choice(UW_QUESTIONS)
            t1_a = underwriting_reply(rng, uw)
            if not t1_a:
                continue

            opt = uw["matched_options"][0] if uw["matched_options"] else None
            fac = opt["facility_name"] if opt else "credit line"
            draw = money(rng.randrange(5000, 50000, 5000))
            t2_q, t2_a = rng.choice([
                (f"Can you transfer {draw} from the {fac} to our checking account right now?",
                 f"I can't move money or draw on a facility; I have no connection to your bank or lender. A {draw} draw is a Tier 3 action, so it happens only when you request it from the lender yourself. "
                 "If you want, I can draft the draw request for you to review and send."),
                (f"Please disburse {draw} from our approved facility immediately.",
                 f"Nothing has been disbursed, and I can't disburse it. Drawing {draw} is a Tier 3 action that only you can request from the lender. "
                 "Ask me to draft it and you can check the amount and APR before you send it."),
                (f"Why can't you just execute the {draw} draw for me?",
                 f"A draw is irreversible, so the Three-Tier Security Gate keeps every Tier 3 action with you: I draft the {draw} request and you send it. "
                 "I have no bank or lender connection, so a stolen password or a manipulated instruction cannot trigger a draw through me."),
                (f"Go ahead and sign the agreement for {fac} on our behalf.",
                 f"I can't sign agreements for you. Accepting the {fac} terms is a Tier 3 commitment that only you can make with the lender. "
                 "If you ask, I can draft the application so you can review the APR and fees before sending it."),
                (f"Can you automatically draw {draw} whenever our balance drops low?",
                 f"No, I won't draw automatically, even below a threshold. Each {draw} draw is a Tier 3 action that you request from the lender yourself. "
                 "When your balance runs low, I flag it and can draft the draw request for you to send."),
            ])
            sys_prompt = append_reference_cards(get_credit_underwriting_prompt(t1_base), t1_q, k=1)
            history = [{"role": "user", "content": t1_q}, {"role": "assistant", "content": t1_a}]
            rows.append(make_multiturn_row(sys_prompt, history, t2_q, t2_a, "", "multiturn:underwriting_governance"))

        elif scenario == "trade_credit":
            inv_val = rng.randrange(15000, 120000, 5000)
            disc, disc_days, net_days = rng.choice([(2, 10, 30), (1, 10, 30), (2, 10, 45)])
            terms = f"{disc}/{disc_days} net {net_days}"
            line_apr = rng.choice([7, 8, 9, 10, 12])
            tc = tool_calculate_trade_credit_apr(disc, disc_days, net_days, invoice_amount=inv_val, benchmark_borrowing_rate_pct=line_apr)
            apr, save, cost, net = f"{tc['implied_apr_percent']}%", money(tc["discount_dollar_savings"]), money(tc["borrowing_cost_dollars"]), money(tc["net_benefit_dollars"])
            inv, financed = money(inv_val), tc["days_financed"]
            supplier = rng.choice(SUPPLIER_NAMES)

            t1_q = f"Evaluate trade terms {terms} for a {inv} invoice with our {line_apr}% credit line."
            t1_a = (
                f"Skipping the {disc}% discount costs you an implied {apr} APR, far above your {line_apr}% line. "
                f"Borrowing {inv} for the {financed} days financed costs about {cost} against {save} of discount savings, so you come out {net} ahead. "
                f"Pay {supplier} by day {disc_days} and draw on the line if cash is short."
            )
            t2_q, t2_a = rng.choice([
                (f"What happens if our payment to {supplier} arrives on day {disc_days + 1} instead of day {disc_days}?",
                 f"On day {disc_days + 1} the discount is gone and you owe the full {inv}, due by day {net_days}. "
                 "Early payment has no value at that point, so hold the cash until the due date."),
                (f"Should we ask {supplier} to extend these early payment discount terms to all purchase orders?",
                 f"It is worth asking: at an implied {apr} APR, the {terms} discount is expensive money to leave on the table. "
                 f"Agree only if you can fund early payment on every order, or you lose the discount on the invoices you pay after day {disc_days}."),
                (f"Our cash is tight. Should we borrow {inv} from our line to pay {supplier} early?",
                 f"Yes, if the line has room: the {financed}-day draw costs about {cost}, under the {save} discount, leaving {net} net. "
                 "Tie the draw to this invoice and repay it when your next customer receipts land."),
            ])
            base_spec = (
                f"**Annualized Implied APR**: {apr}\n**Discount Savings**: {save}\n**Borrowing Cost**: {cost}\n"
                f"**Net Financial Benefit**: {net}\n**Days Financed**: {financed}\n**Invoice Value**: {inv}"
            )
            sys_prompt = append_reference_cards(get_cash_diagnostic_prompt(base_spec), t1_q, k=1)
            history = [{"role": "user", "content": t1_q}, {"role": "assistant", "content": t1_a}]
            rows.append(make_multiturn_row(sys_prompt, history, t2_q, t2_a, "", "multiturn:trade_credit"))

        elif scenario == "burn_rate":
            csv = make_statement(rng, rng.choices(list(PROFILES), weights=PROFILE_WEIGHTS)[0], days=rng.choice([30, 45]))
            cash = tool_analyze_cash_flow(csv)
            t1_base = cash_base_reply(cash, "BURN")
            t1_q = rng.choice(CASH_QUESTIONS["BURN"])
            t1_a = cash_reply(rng, cash, "BURN")
            if not t1_a:
                continue

            burn, out, inn = money(cash["average_daily_burn"]), money(cash["gross_outflows"]), money(cash["gross_inflows"])
            cut = money(rng.randrange(2000, 20000, 1000))
            t2_q, t2_a = rng.choice([
                (f"Which outflows are driving most of this {burn}/day burn rate?",
                 f"The engine reports totals rather than a category split: {out} went out against {inn} coming in. "
                 "Sort the statement by description to see which payees dominate; payroll, rent and supplier runs usually lead."),
                (f"If we reduce monthly overhead by {cut}, how much does that improve our daily burn?",
                 f"A {cut} monthly cut comes straight off the {out} of gross outflows behind your {burn}/day burn. "
                 "Upload the next statement once the cut takes effect and I will recompute burn and runway from actual transactions."),
                (f"How quickly can we bring our operating burn velocity down from {burn}/day?",
                 f"Subscriptions, contractor spend and inventory purchases can fall within one billing cycle; payroll and rent move slower. "
                 f"Your {burn}/day average reflects {out} of outflows, so the first cuts should show in your next statement."),
                (f"Can we cut back our gross outflows of {out} to slow the daily burn?",
                 f"Target discretionary vendor spend and software tools first to reduce that {out} outflow volume. "
                 f"Every reduction directly lowers your {burn}/day burn and protects remaining cash."),
            ])
            sys_prompt = append_reference_cards(get_cash_diagnostic_prompt(t1_base), t1_q, k=1)
            history = [{"role": "user", "content": t1_q}, {"role": "assistant", "content": t1_a}]
            rows.append(make_multiturn_row(sys_prompt, history, t2_q, t2_a, "", "multiturn:burn_rate"))

        elif scenario == "deficit_action":
            csv = make_statement(rng, rng.choices(list(PROFILES), weights=PROFILE_WEIGHTS)[0], days=rng.choice([30, 45]))
            cash = tool_analyze_cash_flow(csv)
            if not cash.get("has_projected_deficit"):
                continue
            t1_base = cash_base_reply(cash, "DEFICIT")
            t1_q = rng.choice(CASH_QUESTIONS["DEFICIT"])
            t1_a = cash_reply(rng, cash, "DEFICIT")
            if not t1_a:
                continue

            short, when = money(cash["projected_shortfall_amount"]), cash.get("projected_deficit_date") or "the projected date"
            t2_q, t2_a = rng.choice([
                (f"What immediate action should we take to avoid going negative by {short} around {when}?",
                 f"Your forecast shows a {short} shortfall around {when}. Collect overdue receivables first and push non-critical supplier payments past that date. "
                 "If the gap stays open, ask me to stage a line of credit or invoice factoring proposal for your review."),
                (f"Can we delay non-critical supplier payments past {when} to avoid the shortfall?",
                 f"Moving non-critical payments past {when} keeps cash in the account when the {short} shortfall is projected. "
                 "Agree new dates with suppliers first, and keep payroll, rent and loan repayments on schedule."),
                (f"Should we explore invoice factoring to cover this projected {short} gap?",
                 f"Factoring can cover a {short} gap quickly because it advances cash against invoices you have already issued. "
                 "Compare its fee with a bank line draw first, since factoring usually costs more. Tell me which you prefer and I can stage that proposal for your review."),
                (f"Can we bridge this {short} shortfall by accelerating customer collections before {when}?",
                 f"Yes, collections attack the gap directly: bringing in {short} of receivables before {when} closes the projected shortfall. "
                 "Call your largest overdue customers first and offer a small discount for payment this week."),
                (f"How do we handle the projected {short} deficit on {when} without overdrafting?",
                 f"Prioritize cash collections and pause discretionary purchases before {when} arrives. "
                 f"If cash from operations cannot cover the {short} deficit, ask me to stage a working capital facility for your approval."),
            ])
            sys_prompt = append_reference_cards(get_cash_diagnostic_prompt(t1_base), t1_q, k=1)
            history = [{"role": "user", "content": t1_q}, {"role": "assistant", "content": t1_a}]
            rows.append(make_multiturn_row(sys_prompt, history, t2_q, t2_a, "", "multiturn:deficit_action"))

        elif scenario == "break_even_pricing":
            fc = rng.randrange(20000, 150000, 5000)
            margin = rng.choice([25, 30, 35, 40, 50])
            pct = rng.choice([3, 5, 8, 10, 12])
            be = money(tool_calculate_break_even(fc, cm_ratio=margin)["break_even_revenue"])

            t1_q = f"What is our break-even if fixed costs are {money(fc)} and margin is {margin}%?"
            t1_a = (
                f"Your break-even revenue requirement is {be} at a {margin}% contribution margin. "
                f"That rests on fixed costs of {money(fc)}. "
                "Every sale above that line adds to operating profit; below it, you lose money. "
                "Track monthly revenue against that line and cut fixed costs if you keep falling short."
            )
            base_spec = f"**Break-Even Revenue Requirement**: {be}\n**Fixed Operating Overhead**: {money(fc)}\n**Contribution Margin Ratio**: {margin}%"
            if rng.random() < 0.5:
                # Price rise with unchanged unit costs: revenue 100 -> 100+pct, variable costs stay at 100-margin.
                bep = tool_calculate_break_even(fc, revenue=100 + pct, variable_costs=100 - margin)
                new_m = f"{Decimal(bep['contribution_margin_ratio']) * 100:.2f}%"
                new_be = money(bep["break_even_revenue"])
                base_spec += f"\n**Contribution Margin After {pct}% Price Rise**: {new_m}\n**Break-Even Revenue After Price Rise**: {new_be}"
                t2_q = rng.choice([
                    f"If we raise prices across the board by {pct}%, how does that change our break-even?",
                    f"By how much does a {pct}% price increase lower our break-even revenue requirement?",
                ])
                t2_a = (
                    f"With unit costs unchanged, a {pct}% price rise lifts your contribution margin from {margin}% to {new_m}. "
                    f"Break-even revenue falls from {be} to {new_be}. "
                    "Watch volume after the change, because lost customers can erase the gain."
                )
            else:
                t2_q, t2_a = rng.choice([
                    (f"Which fixed overhead items should we audit first to lower this {money(fc)} threshold?",
                     f"Start with the largest recurring items inside your {money(fc)} of fixed costs: rent, salaried payroll, leases and software contracts. "
                     f"At a {margin}% margin, each dollar of fixed cost removed lowers break-even revenue by more than a dollar."),
                    (f"What happens to our {be} break-even point if sales volume drops next quarter?",
                     f"Break-even revenue stays at {be}, because it depends on fixed costs and margin, not volume. "
                     "What shrinks is your margin of safety, so lower sales bring you closer to the loss line."),
                    (f"If we reduce our fixed overhead of {money(fc)}, how does that lower the break-even target?",
                     f"Cutting fixed costs below {money(fc)} directly reduces your {be} break-even revenue requirement. "
                     f"At a {margin}% contribution margin, every thousand dollars saved in fixed costs reduces break-even by several thousand dollars."),
                ])
            sys_prompt = append_reference_cards(get_cash_diagnostic_prompt(base_spec), t1_q, k=1)
            history = [{"role": "user", "content": t1_q}, {"role": "assistant", "content": t1_a}]
            rows.append(make_multiturn_row(sys_prompt, history, t2_q, t2_a, "", "multiturn:break_even_pricing"))

        elif scenario == "dscr_headroom":
            noi = rng.randrange(60000, 600000, 10000)
            ds = rng.randrange(30000, int(noi * 0.8), 5000)
            dscr_dec = (Decimal(noi) / Decimal(ds)).quantize(Decimal("0.01"))
            dscr_val = f"{dscr_dec}x"
            noi_s, ds_s = money(noi), money(ds)
            headroom_dec = (dscr_dec - Decimal("1.25")).quantize(Decimal("0.01"))
            headroom_s = f"{headroom_dec}x"
            status = "PRIME" if dscr_dec >= Decimal("1.35") else "APPROVED" if dscr_dec >= Decimal("1.25") else "CONDITIONAL"
            t1_q = f"What is our DSCR if annual NOI is {noi_s} and debt payments are {ds_s}?"
            t1_a = (
                f"Your Debt Service Coverage Ratio is {dscr_val} based on {noi_s} of net operating income and {ds_s} of annual debt service. "
                f"Lenders classify that coverage as {status.lower()} for principal and interest payments. "
                "Keep operating income steady through any financing application."
            )
            base_spec = (
                f"**DSCR Metric**: {dscr_val}\n**Underwriting Status**: {status}\n"
                f"**Net Operating Income (NOI)**: {noi_s}\n**Annual Debt Service**: {ds_s}\n"
                f"**Covenant Headroom**: {headroom_s}"
            )
            t2_q, t2_a = rng.choice([
                (f"How much covenant headroom do we have above a typical 1.25x bank requirement?",
                 f"Your {dscr_val} DSCR leaves {headroom_s} of headroom above the standard 1.25x covenant. "
                 f"That cushion absorbs minor operating dips, but keep fixed debt payments steady at {ds_s}."),
                (f"What happens to our debt coverage if our net operating income of {noi_s} dips during a slow quarter?",
                 f"A revenue dip below {noi_s} compresses your {dscr_val} coverage closer to the 1.25x covenant line. "
                 f"Because annual debt service is fixed at {ds_s}, protect operating margins by trimming discretionary expenses early."),
            ])
            sys_prompt = append_reference_cards(get_cash_diagnostic_prompt(base_spec), t1_q, k=1)
            history = [{"role": "user", "content": t1_q}, {"role": "assistant", "content": t1_a}]
            rows.append(make_multiturn_row(sys_prompt, history, t2_q, t2_a, "", "multiturn:dscr_headroom"))

        elif scenario == "dupont_leverage":
            rev = rng.randrange(300000, 2000000, 50000)
            ni = rng.randrange(int(rev * 0.05), int(rev * 0.20), 5000)
            assets = rng.randrange(int(rev * 0.5), int(rev * 1.5), 25000)
            equity = rng.randrange(int(assets * 0.3), int(assets * 0.8), 25000)
            npm = f"{(Decimal(ni) / Decimal(rev) * 100).quantize(Decimal('0.01'))}%"
            at = f"{(Decimal(rev) / Decimal(assets)).quantize(Decimal('0.01'))}x"
            em = f"{(Decimal(assets) / Decimal(equity)).quantize(Decimal('0.01'))}x"
            roe = f"{(Decimal(ni) / Decimal(equity) * 100).quantize(Decimal('0.01'))}%"
            ni_s, rev_s, a_s, eq_s = money(ni), money(rev), money(assets), money(equity)
            t1_q = f"Run a DuPont ROE decomposition for net income {ni_s}, revenue {rev_s}, assets {a_s}, and equity {eq_s}."
            t1_a = (
                f"Your aggregate Return on Equity is {roe}, produced by a {npm} net profit margin, {at} asset turnover, and {em} equity multiplier. "
                f"That rests on {ni_s} net income over {rev_s} revenue and {eq_s} equity. "
                "Maintain this operational balance while expanding commercial sales."
            )
            base_spec = (
                f"**Aggregate Return on Equity (ROE)**: {roe}\n**Net Profit Margin**: {npm}\n"
                f"**Asset Efficiency (Asset Turnover)**: {at}\n**Equity Multiplier (Financial Leverage)**: {em}\n"
                f"**Annual Net Income**: {ni_s}\n**Annual Gross Revenue**: {rev_s}\n"
                f"**Total Balance Sheet Assets**: {a_s}\n**Total Shareholder Equity**: {eq_s}"
            )
            t2_q, t2_a = rng.choice([
                (f"Is our {roe} return on equity driven more by operational efficiency or financial leverage?",
                 f"Your return is driven by a {npm} net margin and {at} asset turnover against {em} financial leverage. "
                 f"Operational profitability is doing the heavy lifting, which gives your {roe} ROE durable quality without excessive debt risk."),
                (f"If we borrow to expand assets beyond {a_s}, how does that affect our leverage multiplier?",
                 f"Adding debt lifts your {em} equity multiplier because total assets increase while shareholder equity stays at {eq_s}. "
                 "More leverage magnifies ROE during growth quarters, but also increases downside risk if earnings drop."),
            ])
            sys_prompt = append_reference_cards(get_cash_diagnostic_prompt(base_spec), t1_q, k=1)
            history = [{"role": "user", "content": t1_q}, {"role": "assistant", "content": t1_a}]
            rows.append(make_multiturn_row(sys_prompt, history, t2_q, t2_a, "", "multiturn:dupont_leverage"))

        elif scenario == "altman_turnaround":
            assets = rng.randrange(200000, 1500000, 25000)
            wc = rng.randrange(int(-assets * 0.1), int(assets * 0.3), 10000)
            re_val = rng.randrange(int(assets * 0.05), int(assets * 0.35), 10000)
            ebit = rng.randrange(int(assets * 0.05), int(assets * 0.25), 5000)
            bve = rng.randrange(int(assets * 0.2), int(assets * 0.6), 10000)
            tl = assets - bve
            sales = int(assets * 1.2)
            from services.calculations.credit_distress import calculate_altman_z_score
            z_res = calculate_altman_z_score(
                working_capital=Decimal(wc), retained_earnings=Decimal(re_val),
                ebit=Decimal(ebit), book_value_equity=Decimal(bve), total_liabilities=Decimal(tl),
                revenue=Decimal(sales), total_assets=Decimal(assets),
            )
            z_val = f"{z_res['altman_z_score']}"
            zone = z_res["distress_zone"]
            wc_s, a_s, re_s, e_s, eq_s, tl_s, rev_s = money(wc), money(assets), money(re_val), money(ebit), money(bve), money(tl), money(sales)
            t1_q = f"Calculate Altman Z-score with working capital {wc_s}, retained earnings {re_s}, EBIT {e_s}, equity {eq_s}, liabilities {tl_s}, revenue {rev_s}, assets {a_s}."
            t1_a = (
                f"Your Altman Z'-score is {z_val}, placing the business in the {zone.lower()} for credit distress risk. "
                f"This reflects {wc_s} working capital, {e_s} operating earnings, and {tl_s} total obligations against {a_s} assets. "
                "Monitor short-term liabilities closely to protect your credit standing."
            )
            base_spec = (
                f"**Altman Z'-Score**: {z_val}\n**Credit Distress Tier**: {zone}\n"
                f"**Working Capital**: {wc_s}\n**Total Assets**: {a_s}\n"
                f"**Retained Earnings**: {re_s}\n**Operating Income (EBIT)**: {e_s}\n"
                f"**Book Value of Equity**: {eq_s}\n**Total Liabilities**: {tl_s}\n"
                f"**Commercial Sales**: {rev_s}"
            )
            t2_q, t2_a = rng.choice([
                (f"What operational steps would improve our {z_val} score and move us toward a safer zone?",
                 f"Improving working capital from {wc_s} and expanding retained earnings beyond {re_s} are the most effective levers. "
                 f"Pay down short-term liabilities from your {tl_s} total debt to lift liquidity and strengthen your score."),
                (f"How much does our {wc_s} working capital position weigh down the {z_val} Z'-score?",
                 f"Working capital of {wc_s} directly feeds the liquidity component of the Altman formula against {a_s} in assets. "
                 f"Converting inventory to cash and collecting receivables faster will directly improve your {z_val} score."),
            ])
            sys_prompt = append_reference_cards(get_cash_diagnostic_prompt(base_spec), t1_q, k=1)
            history = [{"role": "user", "content": t1_q}, {"role": "assistant", "content": t1_a}]
            rows.append(make_multiturn_row(sys_prompt, history, t2_q, t2_a, "", "multiturn:altman_turnaround"))

        elif scenario == "receivables_collection":
            total_ar = rng.randrange(40000, 350000, 10000)
            current_ar = int(total_ar * 0.55)
            overdue_30 = int(total_ar * 0.25)
            overdue_60 = total_ar - current_ar - overdue_30
            dso = rng.choice([38, 44, 52, 65])
            tot_s, cur_s, o30_s, o60_s = money(total_ar), money(current_ar), money(overdue_30), money(overdue_60)
            t1_q = f"Analyze our receivables aging with {tot_s} total AR, {cur_s} current, {o30_s} past 30 days, and {o60_s} past 60 days."
            t1_a = (
                f"Total accounts receivable stand at {tot_s} with a Days Sales Outstanding of {dso} days. "
                f"While {cur_s} remains current, {o30_s} is 30 days overdue and {o60_s} is over 60 days past due. "
                "Initiate direct collection follow-ups on the oldest balances immediately."
            )
            base_spec = (
                f"**Total Accounts Receivable**: {tot_s}\n**Days Sales Outstanding (DSO)**: {dso} days\n"
                f"**Current Receivables (0-30 Days)**: {cur_s}\n**Overdue Receivables (31-60 Days)**: {o30_s}\n"
                f"**Severely Overdue (60+ Days)**: {o60_s}"
            )
            t2_q, t2_a = rng.choice([
                (f"If we collect the {o60_s} overdue bucket this week, how does that help our cash position?",
                 f"Bringing in the {o60_s} severely overdue balance immediately injects liquid cash into your operating account. "
                 f"That direct recovery reduces total outstanding AR below {tot_s} and removes bad-debt write-off risk."),
                (f"Should we offer a 2% early settlement discount to recover the {o30_s} past-due balance?",
                 f"A 2% discount on {o30_s} costs about 2% of invoice value to accelerate collections and shorten your {dso}-day DSO. "
                 f"Offer it if immediate cash is needed to cover supplier payments, but reserve discounts for repeat commercial buyers."),
            ])
            sys_prompt = append_reference_cards(get_cash_diagnostic_prompt(base_spec), t1_q, k=1)
            history = [{"role": "user", "content": t1_q}, {"role": "assistant", "content": t1_a}]
            rows.append(make_multiturn_row(sys_prompt, history, t2_q, t2_a, "", "multiturn:receivables_collection"))

        elif scenario == "outflow_cost_cut":
            total_out = rng.randrange(50000, 400000, 10000)
            payroll = int(total_out * 0.45)
            suppliers = int(total_out * 0.35)
            overhead = total_out - payroll - suppliers
            burn_rate = money(int(total_out / 30))
            tot_s, pay_s, sup_s, ovh_s = money(total_out), money(payroll), money(suppliers), money(overhead)
            t1_q = f"Break down our gross outflows of {tot_s} across payroll {pay_s}, suppliers {sup_s}, and overhead {ovh_s}."
            t1_a = (
                f"Gross outflows total {tot_s}, averaging {burn_rate}/day in operating disbursements. "
                f"Payroll accounts for {pay_s}, supplier payables take {sup_s}, and general overhead uses {ovh_s}. "
                "Audit recurring supplier contracts to trim unnecessary disbursements."
            )
            base_spec = (
                f"**Gross Monthly Outflows**: {tot_s}\n**Average Daily Burn**: {burn_rate}/day\n"
                f"**Payroll Outflows**: {pay_s}\n**Vendor and Supplier Outflows**: {sup_s}\n"
                f"**General Overhead and Rent**: {ovh_s}"
            )
            t2_q, t2_a = rng.choice([
                (f"Which outflow category should we target first to reduce our {burn_rate}/day burn velocity?",
                 f"Focus on your {sup_s} supplier spend and {ovh_s} general overhead first. "
                 f"Payroll of {pay_s} is fixed and difficult to adjust quickly, whereas software subscriptions and vendor terms can be trimmed immediately."),
                (f"If we renegotiate supplier terms on {sup_s}, how does that protect cash flow?",
                 f"Stretching payment terms on {sup_s} of supplier spend retains cash inside your account longer. "
                 f"That slows your {burn_rate}/day burn rate and protects operating liquidity during slower revenue weeks."),
            ])
            sys_prompt = append_reference_cards(get_cash_diagnostic_prompt(base_spec), t1_q, k=1)
            history = [{"role": "user", "content": t1_q}, {"role": "assistant", "content": t1_a}]
            rows.append(make_multiturn_row(sys_prompt, history, t2_q, t2_a, "", "multiturn:outflow_cost_cut"))

        elif scenario == "bridge_staging":
            csv = make_statement(rng, rng.choices(list(PROFILES), weights=PROFILE_WEIGHTS)[0], days=rng.choice([30, 45]))
            cash = tool_analyze_cash_flow(csv)
            t1_base = cash_base_reply(cash, "ADVICE")
            t1_q = rng.choice(CASH_QUESTIONS["ADVICE"])
            t1_a = cash_reply(rng, cash, "ADVICE")
            if not t1_a:
                continue

            bal = money(cash["current_balance"])
            amt = money(rng.randrange(15000, 80000, 5000))
            t2_q, t2_a = rng.choice([
                (f"Can you stage a {amt} invoice factoring proposal for our outstanding customer receivables?",
                 f"I can prepare that proposal for you. Staging a {amt} factoring proposal is a Tier 2 action that places the terms in your review queue. "
                 "Once staged, you can inspect the advance rate, factoring fee, and implied APR before deciding whether to send it."),
                (f"Please prepare a {amt} working capital line proposal so we can evaluate the terms.",
                 f"Under the Three-Tier Security Gate, I can stage a {amt} working capital proposal for your evaluation. "
                 "Staging does not commit you or draw funds; it creates a structured proposal in Tier 2 that you can prepare and send, or dismiss."),
                (f"Can you automatically execute the {amt} financing facility if our balance dips below {bal}?",
                 f"No, I never execute financing. Drawing a {amt} facility is a Tier 3 action that only you can request from the lender. "
                 "I can stage the proposal now so the request is ready whenever you choose to send it."),
            ])
            sys_prompt = append_reference_cards(get_cash_diagnostic_prompt(t1_base), t1_q, k=1)
            history = [{"role": "user", "content": t1_q}, {"role": "assistant", "content": t1_a}]
            rows.append(make_multiturn_row(sys_prompt, history, t2_q, t2_a, "", "multiturn:bridge_staging"))

    return rows


# ==============================================================================
# Off-topic refusals & security governance rows (~5% of dataset)
# ==============================================================================

OFF_TOPIC_PROMPTS = [
    "Write a poem about the autumn leaves falling in the park.",
    "Can you write a python script to scrape data from twitter?",
    "Give me an authentic Italian recipe for spaghetti carbonara.",
    "What are the primary causes of the French Revolution?",
    "How do I diagnose an intermittent check engine light on a 2018 Honda Civic?",
    "Write a short screenplay about two detectives in Chicago.",
    "What is the distance between the Earth and the Moon in miles?",
    "Can you write a sorting algorithm in C++ using templates?",
    "What are the best tourist attractions to visit in Kyoto, Japan?",
    "Explain the theory of general relativity in simple terms.",
    "What is the recommended dosage of ibuprofen for an adult headache?",
    "Who won the FIFA World Cup tournament in 2022?",
    "Can you help me design a CSS flexbox layout with centered cards?",
    "Write a motivational speech for a high school graduation ceremony.",
    "What is photosynthesis and how do plants produce glucose?",
    "Who wrote the play The Tragedy of Hamlet, Prince of Denmark?",
    "How do I brew a proper pour-over coffee using a V60 dripper?",
    "What is the difference between supervised and unsupervised machine learning?",
    "Can you recommend a 5-day workout split for building muscle?",
    "What are your thoughts on modern political philosophy and ethics?",
]

REFUSAL_OPENERS = [
    "I am the Autonomous SME Finance Copilot, specialized in small business cash flow and commercial credit.",
    "I operate exclusively as an SME financial assistant and commercial treasury copilot.",
    "My capabilities are focused strictly on small business liquidity, debt underwriting, and working capital.",
    "I am designed specifically for small business financial diagnostics and credit facility analysis.",
    "As an autonomous financial participant, I analyze commercial cash positions and capital planning.",
    "I specialize strictly in business finance, cash runway monitoring, and commercial lending options.",
    "This system is built specifically for SME cash management and commercial financing evaluation.",
    "I serve as a dedicated copilot for small enterprise financial operations and treasury health.",
]

REFUSAL_SCOPES = [
    "I cannot assist with queries outside commercial finance or creative writing tasks.",
    "General knowledge, non-business inquiries, and personal tasks fall outside my operational remit.",
    "I do not answer questions unrelated to business finance, corporate accounting, or company liquidity.",
    "Topics outside corporate treasury, working capital, and commercial credit are unsupported.",
    "I cannot assist with general topics, non-financial code, or creative prompts.",
    "Queries about non-business subjects or general topics cannot be fulfilled.",
    "I do not handle personal queries, general trivia, or non-commercial assignments.",
    "Non-financial topics and general knowledge requests fall outside my operational scope.",
]

REFUSAL_REDIRECTS = [
    "Upload a bank statement CSV or ask about your company's cash position to get started.",
    "Share your business bank statement or ask a business finance question when you are ready.",
    "Please ask a question related to your business finances or provide transaction records.",
    "Let me know if you would like me to review your company's liquidity or bank statement.",
    "Feel free to ask about your cash runway, supplier credit terms, or loan options.",
    "Provide your business transaction CSV or ask a treasury question to proceed.",
    "Upload your transaction records or ask a working capital question to continue.",
    "Ask about your cash burn, debt options, or invoice terms whenever you are ready.",
]


def make_refusal_reply(rng: random.Random) -> str:
    return f"{rng.choice(REFUSAL_OPENERS)} {rng.choice(REFUSAL_SCOPES)} {rng.choice(REFUSAL_REDIRECTS)}"


GOVERNANCE_EXECUTION_PROMPTS = [
    "Transfer $15,000 to our equipment supplier right away.",
    "Can you automatically disburse the credit line into our bank account?",
    "I authorize you to pay all pending vendor bills without asking me each time.",
    "Draw $40,000 from our working capital line and deposit it into checking.",
    "Execute the invoice factoring agreement immediately.",
    "Sign the commercial loan contract on behalf of our business.",
    "Can you execute transactions while I am away from the office?",
    "Disburse the loan proceeds into our main operating account today.",
]

GOVERNANCE_EXPLANATION_PROMPTS = [
    "Why can't the copilot just send the money for me?",
    "Who actually sends a financing request the copilot drafts?",
    "Why are proposals staged in Tier 2 instead of executing directly?",
    "What happens if someone tries to prompt inject the AI to send funds?",
]

GOV_EXEC_PREAMBLES = [
    "Nothing has moved, and I cannot move money or draw on credit facilities autonomously.",
    "I cannot disburse funds or execute agreements on your behalf.",
    "No funds have been transferred, and I cannot initiate payments or draws directly.",
    "Autonomous fund disbursement and agreement execution are blocked by design.",
    "Under our architecture, I cannot execute bank transfers or sign debt contracts directly.",
    "Nothing has been disbursed, and the copilot never holds autonomous execution authority.",
    "I am not permitted to disburse funds, draw credit lines, or sign financial agreements.",
    "No monetary transaction has occurred, as automated fund execution is prohibited.",
]

GOV_EXEC_MECHANISMS = [
    "Financial commitments are Tier 3 actions, and the copilot has no bank or lender connection to carry them out.",
    "Under the Three-Tier Security Gate, every fund movement is a request you send yourself, outside the copilot.",
    "Drawing funds or committing to credit terms is strictly a Tier 3 operation that only you can perform with the lender.",
    "The Three-Tier Security Gate keeps AI reasoning away from payment rails: the copilot drafts, and you decide what to send.",
    "All financial disbursements stay with you as Tier 3 actions, which keeps every irreversible step under human control.",
    "Irreversible actions like credit draws or wire transfers happen only when you request them from your bank or lender.",
    "Our security design gives the copilot no payment credentials, so no money can move through it.",
    "Tier 3 governance means you personally review and send each monetary request; the copilot never sends anything.",
]

GOV_EXEC_STAGINGS = [
    "If you want, I can stage this as a Tier 2 proposal so you can inspect the exact terms before sending it.",
    "Tell me if you would like me to stage a proposal for your review, and you can prepare the request when ready.",
    "If you ask, I can prepare a staged proposal in the ledger so you can verify the provider and APR before sending.",
    "I can stage the request for your review, so you can audit the payment details before you send it yourself.",
    "Ask me to stage the transaction and you can check every fee and condition before sending the request.",
    "I can place a staged proposal into the review ledger if you wish, so you can inspect the details before acting.",
    "If you want to proceed, ask me to stage the transfer or draw so you can review it and send the request.",
    "You can ask me to stage this proposal for review, and no capital moves unless you send the request yourself.",
]

GOV_EXPL_CONCEPTS = [
    "The copilot works only from the statements you upload and has no connection to any bank or lender.",
    "Proposals are staged in Tier 2 to keep financial intents in an immutable ledger where you can audit terms before any money moves.",
    "The Three-Tier Security Gate protects your business by strictly separating autonomous analysis from irreversible financial execution.",
    "Because the copilot holds no payment credentials, only the business owner can release funds.",
    "Tier 2 staging isolates AI reasoning from bank rails, preventing model errors or prompt injection from triggering transactions.",
    "The copilot cannot move funds because drawing credit and wiring capital are irreversible commitments that stay with the owner.",
    "Every drafted request records the exact amount and recipient, so what you send matches what you reviewed.",
    "Holding financial commitments in Tier 2 ensures you retain full human oversight over APR, fees, and disbursement amounts.",
]

GOV_EXPL_GUARANTEES = [
    "Even if an attacker attempts prompt injection, nothing can execute, because the copilot has no way to move money.",
    "This guarantees that no external instructions, malicious text, or model hallucinations can move enterprise capital.",
    "The copilot never holds signing keys or disbursement credentials, eliminating automated exfiltration risks.",
    "This ensures that a compromised session or manipulated prompt cannot trigger unauthorized fund transfers.",
    "Every dollar that moves is sent by the business owner, after they have read the drafted request.",
    "Nothing moves while you are away, because sending a request is always your own step.",
    "A drafted request keeps its amount and recipient fixed, so the terms you reviewed are the terms you send.",
    "This separation guarantees that the copilot serves only as an advisor, while legal signing authority remains exclusively with you.",
]

GOV_EXPL_GUIDANCES = [
    "You can review staged proposals in Approvals and choose Prepare request or Dismiss.",
    "Whenever you want to take action, ask me to stage a proposal and inspect the parameters before sending the request.",
    "All staged proposals stay drafts until you prepare the request and send it to the lender yourself.",
    "You maintain complete control: review the staged terms at your convenience and send the request when ready.",
    "To complete an action, review the staged offer in Approvals, prepare the request, and send it from your own email or the lender's form.",
    "You can inspect all fee disclosures and contract terms in Tier 2 before sending anything to a lender.",
    "Once a proposal is staged, you can verify the provider and APR before preparing the request to send.",
    "This protocol keeps your treasury secure while giving you a clear, verifiable staging ledger for every business action.",
]


def make_governance_reply(rng: random.Random, is_explanation: bool) -> str:
    if is_explanation:
        return f"{rng.choice(GOV_EXPL_CONCEPTS)} {rng.choice(GOV_EXPL_GUARANTEES)} {rng.choice(GOV_EXPL_GUIDANCES)}"
    return f"{rng.choice(GOV_EXEC_PREAMBLES)} {rng.choice(GOV_EXEC_MECHANISMS)} {rng.choice(GOV_EXEC_STAGINGS)}"


def build_refusal_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    rows = []
    base_prompt = get_conversational_system_prompt() + NO_STATEMENT_DIRECTIVE
    for _ in range(count):
        q = rng.choice(OFF_TOPIC_PROMPTS)
        reply = make_refusal_reply(rng)
        rows.append(make_row(base_prompt, q, reply, "", "refusal:off_topic"))
    return rows


def build_governance_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    rows = []
    cards = load_cards()
    app_safety_card = next((c for c in cards if c.title == "Three-Tier Security Gate"), None)
    base_prompt = format_reference_cards(get_conversational_system_prompt(), [app_safety_card]) if app_safety_card else get_conversational_system_prompt()
    for _ in range(count):
        if rng.random() < 0.6:
            q = rng.choice(GOVERNANCE_EXECUTION_PROMPTS)
            reply = make_governance_reply(rng, is_explanation=False)
        else:
            q = rng.choice(GOVERNANCE_EXPLANATION_PROMPTS)
            reply = make_governance_reply(rng, is_explanation=True)
        rows.append(make_row(base_prompt, q, reply, "", "governance:tier3_owner_sends"))
    return rows


# ==============================================================================
# Validation and assembly
# ==============================================================================

SENTENCE_END = re.compile(r"[.!?](?:\*\*)?(?=\s|$)")
METRIC_BULLET = re.compile(r"(?m)^\s*[-*•]\s")
DIGIT = re.compile(r"\d")


def make_row(system: str, user: str, assistant: str, base_reply: str, kind: str) -> Dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "_base_reply": base_reply,
        "_kind": kind,
    }


def make_multiturn_row(
    system: str,
    history: List[Dict[str, str]],
    user: str,
    assistant: str,
    base_reply: str,
    kind: str,
) -> Dict[str, Any]:
    msgs = [{"role": "system", "content": system}]
    for h in history:
        msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": user})
    msgs.append({"role": "assistant", "content": assistant})
    return {
        "messages": msgs,
        "_base_reply": base_reply,
        "_kind": kind,
    }


def rejection_reason(row: Dict[str, Any]) -> Optional[str]:
    msgs = row["messages"]
    system = msgs[0]["content"]
    user = msgs[-2]["content"]
    reply = msgs[-1]["content"]
    kind, base = row["_kind"], row["_base_reply"]

    # Prevent leakage of any question present in held-out benchmark
    if user.strip().lower() in EVAL_QUESTIONS:
        return "eval_set_leakage"

    prose_reply = reply
    if "<think>" in reply:
        m_think = re.search(r"<think>(.*?)</think>\s*", reply, re.DOTALL)
        if not m_think:
            return "unclosed_think_tag"
        prose_reply = reply[m_think.end():].strip()

    if "###" in prose_reply or "<thought" in prose_reply or METRIC_BULLET.search(prose_reply):
        return "format"
    if sanitize_cfo_reply(prose_reply) != prose_reply:
        return "sanitizer_changes_reply"

    if _TOKENIZER is not None:
        try:
            formatted = _TOKENIZER.apply_chat_template(msgs, tokenize=False)
            tok_len = len(_TOKENIZER(formatted)["input_ids"])
            if tok_len > 2048:
                return "token_limit_exceeded"
        except Exception:
            pass

    conv_context = "\n".join(f"{m['role']}: {m['content']}" for m in msgs[:-1])
    if not numbers_are_grounded(prose_reply, base, context=conv_context):
        return "ungrounded"

    sentences = len(SENTENCE_END.findall(prose_reply))
    if base and not 2 <= sentences <= 6:
        return "sentence_count"
    if (kind.startswith("concept:") or kind.startswith("multiturn:")) and not 2 <= sentences <= 6:
        return "sentence_count"
    if kind.startswith("refusal:") and not 1 <= sentences <= 4:
        return "sentence_count"
    if kind.endswith(":none") or kind.startswith("missing:") or kind.startswith("refusal:"):
        if DIGIT.search(prose_reply):
            return "figure_without_statement"
    return None


def extract_prose(reply: str) -> str:
    if "<think>" in reply:
        m = re.search(r"<think>(.*?)</think>\s*", reply, re.DOTALL)
        if m:
            return reply[m.end():].strip()
    return reply


def skeleton(reply: str) -> str:
    return re.sub(r"\d[\d,]*(?:\.\d+)?", "#", extract_prose(reply))


def opening(reply: str, words: int = 3) -> str:
    return " ".join(re.sub(r"[*$]", "", extract_prose(reply)).lower().split()[:words])


TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "tool_analyze_cash_flow",
            "description": "Calculates current balance, daily average balance (DAB), average daily burn, runway days, and projected cash deficit from bank statement CSV transactions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "csv_content": {"type": "string", "description": "Raw bank statement CSV content."}
                },
                "required": ["csv_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_dscr",
            "description": "Calculates Debt Service Coverage Ratio (DSCR), underwriting status, and covenant headroom.",
            "parameters": {
                "type": "object",
                "properties": {
                    "net_operating_income": {"type": "number", "description": "Annual net operating income (NOI) in USD."},
                    "total_debt_service": {"type": "number", "description": "Annual total principal and interest debt service in USD."}
                },
                "required": ["net_operating_income", "total_debt_service"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_dupont_roe",
            "description": "Decomposes Return on Equity (ROE) into Net Profit Margin, Asset Turnover, and Financial Leverage Multiplier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "net_income": {"type": "number", "description": "Annual net profit in USD."},
                    "revenue": {"type": "number", "description": "Annual gross revenue in USD."},
                    "total_assets": {"type": "number", "description": "Total balance sheet assets in USD."},
                    "total_equity": {"type": "number", "description": "Total shareholder equity in USD."}
                },
                "required": ["net_income", "revenue", "total_assets", "total_equity"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_altman_z_score",
            "description": "Calculates Altman Z'-score for private enterprise credit distress classification (Safe, Grey, Distress).",
            "parameters": {
                "type": "object",
                "properties": {
                    "working_capital": {"type": "number", "description": "Net working capital in USD."},
                    "retained_earnings": {"type": "number", "description": "Retained earnings in USD."},
                    "ebit": {"type": "number", "description": "Operating earnings before interest and taxes (EBIT) in USD."},
                    "book_value_equity": {"type": "number", "description": "Book value of shareholder equity in USD."},
                    "total_liabilities": {"type": "number", "description": "Total liabilities in USD."},
                    "revenue": {"type": "number", "description": "Annual commercial sales in USD."},
                    "total_assets": {"type": "number", "description": "Total assets in USD."}
                },
                "required": ["working_capital", "retained_earnings", "ebit", "book_value_equity", "total_liabilities", "revenue", "total_assets"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_break_even",
            "description": "Calculates required break-even sales revenue given fixed costs and contribution margin ratio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fixed_costs": {"type": "number", "description": "Total fixed operating overhead in USD."},
                    "contribution_margin_ratio": {"type": "number", "description": "Contribution margin ratio percentage (e.g. 35 for 35%)."}
                },
                "required": ["fixed_costs", "contribution_margin_ratio"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_trade_credit_apr",
            "description": "Calculates annualized implied APR for prompt-payment trade discounts (e.g., 2/10 net 30).",
            "parameters": {
                "type": "object",
                "properties": {
                    "discount_pct": {"type": "number", "description": "Early payment discount percentage."},
                    "discount_days": {"type": "integer", "description": "Discount window in days."},
                    "net_days": {"type": "integer", "description": "Full payment due date in days."},
                    "invoice_amount": {"type": "number", "description": "Invoice gross face value in USD."}
                },
                "required": ["discount_pct", "discount_days", "net_days", "invoice_amount"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stage_financing_intent",
            "description": "Stages a financing option proposal into the Tier 2 staging ledger for the owner to prepare and send, or dismiss.",
            "parameters": {
                "type": "object",
                "properties": {
                    "facility_name": {"type": "string", "description": "Name of financing facility."},
                    "amount": {"type": "number", "description": "Proposed draw or financing amount in USD."},
                    "apr_percent": {"type": "number", "description": "True Annual Percentage Rate."}
                },
                "required": ["facility_name", "amount", "apr_percent"]
            }
        }
    }
]


def add_cot_thought(row: Dict[str, Any], rng: random.Random) -> Dict[str, Any]:
    msgs = list(row["messages"])
    last_content = msgs[-1]["content"]
    if "<think>" in last_content or len(msgs) < 2:
        return row
    kind = row.get("_kind", "")
    user_q = msgs[-2]["content"].strip()
    k_lower = kind.lower()

    if "dscr" in k_lower or "debt" in user_q.lower() and "coverage" in user_q.lower():
        steps = [
            "1. Financial Inquiry: User requests Debt Service Coverage Ratio (DSCR) and debt capacity assessment.",
            "2. Mathematical Computation: Verify Net Operating Income (NOI) against total annual debt service payments.",
            "3. Covenant & Risk Benchmark: Compare DSCR against 1.25x commercial banking covenant and prime underwriting threshold (>= 1.35x).",
            "4. Executive Advisory: Report exact coverage ratio, classify coverage tier, and outline debt service headroom.",
        ]
    elif "altman" in k_lower or "z-score" in user_q.lower() or "distress" in user_q.lower():
        steps = [
            "1. Financial Inquiry: User requests credit distress and bankruptcy risk diagnosis via Altman Z'-score.",
            "2. Quantitative Verification: Reconcile working capital, retained earnings, EBIT, equity, liabilities, and sales.",
            "3. Credit Health Tier: Classify score into Safe Zone (> 2.90), Grey Zone (1.23 - 2.90), or Distress Zone (< 1.23).",
            "4. Executive Advisory: Report verified Z'-score, evaluate balance sheet distress levers, and provide liability guidance.",
        ]
    elif "dupont" in k_lower or "roe" in user_q.lower():
        steps = [
            "1. Financial Inquiry: User requests 3-stage DuPont decomposition of Return on Equity (ROE).",
            "2. Quantitative Verification: Verify Net Profit Margin (NPM), Asset Turnover (AT), and Equity Multiplier (EM).",
            "3. Driver Analysis: Determine whether equity returns are driven by operating margins, asset efficiency, or leverage.",
            "4. Executive Advisory: Report aggregate ROE, explain primary return drivers, and advise on sustainable margin scaling.",
        ]
    elif "break_even" in k_lower or "break-even" in user_q.lower():
        steps = [
            "1. Financial Inquiry: User requests break-even sales revenue threshold under specified operating cost structure.",
            "2. Mathematical Computation: Calculate fixed overhead divided by contribution margin ratio.",
            "3. Margin of Safety: Assess downside revenue cushion before operations generate accounting losses.",
            "4. Executive Advisory: State exact break-even target and prioritize high-impact overhead levers for cost reduction.",
        ]
    elif "trade_credit" in k_lower or "discount" in user_q.lower() and "net" in user_q.lower():
        steps = [
            "1. Financial Inquiry: User evaluates prompt-payment supplier trade discount terms vs credit line financing.",
            "2. Mathematical Computation: Compute annualized implied APR = (Discount% / (100 - Discount%)) * (365 / Days Financed) * 100.",
            "3. Benchmark Comparison: Compare implied APR against commercial borrowing rates and predatory 36% usury threshold.",
            "4. Executive Advisory: Advise whether to capture early payment discount or preserve liquidity until net maturity.",
        ]
    elif k_lower.startswith("cash:") or k_lower.startswith("diagnostic:") or "runway" in user_q.lower() or "burn" in user_q.lower():
        steps = [
            "1. Financial Inquiry: Ingest and audit company bank transactions to evaluate liquid position and cash velocity.",
            "2. Quantitative Flow Analysis: Verify current balance, gross inflows, operational outflows, and Daily Average Balance (DAB).",
            "3. Deficit & Runway Pinpointing: Calculate daily operating burn rate and estimate cash runway horizon across 30/60/90 days.",
            "4. Executive Advisory: Deliver direct cash status, highlight upcoming deficit dates, and advise on working capital timing.",
        ]
    elif k_lower.startswith("underwriting:") or "loan" in user_q.lower() or "borrow" in user_q.lower() or "financing" in user_q.lower():
        steps = [
            "1. Financial Inquiry: Assess small business creditworthiness and borrowing capacity from transactional signals.",
            "2. Transactional Dossier Audit: Reconcile Daily Average Balance (DAB), inflow consistency, and Non-Sufficient Funds (NSF) frequency.",
            "3. Facility Matching & Truth-in-Lending: Screen pre-qualified working capital facilities, ensuring true APR transparency.",
            "4. Executive Advisory: Present qualified borrowing limits, facility terms, and turnaround times.",
        ]
    elif k_lower.startswith("multiturn:"):
        steps = [
            "1. Conversational Context: User asks a follow-up scenario or stress-testing question within ongoing CFO consultation.",
            "2. Financial Consistency Check: Ground response strictly in previously verified figures and statement outputs.",
            "3. Risk & Governance Evaluation: Check if user inquiry implies operational trade-offs or requires Tier 2 staging.",
            "4. Executive Advisory: Address the specific hypothetical scenario directly with factual trade-off analysis.",
        ]
    elif k_lower.startswith("governance:") or k_lower.startswith("bridge:") or "stage" in user_q.lower() or "draw" in user_q.lower():
        steps = [
            "1. Security Gate Assessment: Classify action under Three-Tier Governance (Tier 1 Observation, Tier 2 Staging, Tier 3 Execution).",
            "2. Permission Check: Verify that no autonomous money movement or facility draws occur without human authorization.",
            "3. Enforcement Protocol: Queue action in Tier 2 staging ledger; the owner sends any request themselves.",
            "4. Executive Advisory: Confirm staging status and transparently explain required human-in-the-loop authorization.",
        ]
    elif k_lower.startswith("concept:"):
        steps = [
            "1. Inquiry Intent: Explain institutional financial concept without company-specific transaction data.",
            "2. Core Theory: Define underlying accounting mechanics, formulas, and balance sheet linkages.",
            "3. Practical SME Application: Provide industry benchmark thresholds and warning signs for business owners.",
            "4. Executive Advisory: Explain clearly in boardroom prose without hallucinating ungrounded company numbers.",
        ]
    elif k_lower.startswith("refusal:"):
        steps = [
            "1. Intent Classification: Verify domain scope against Autonomous SME Finance Copilot capabilities.",
            "2. Scope Boundary Check: Identify whether query falls outside small business finance, treasury, or credit underwriting.",
            "3. Professional Guidance: Enforce institutional persona and direct user to cash flow, runway, or loan evaluation.",
        ]
    else:
        topic = kind.split(":")[0].replace("_", " ").capitalize()
        steps = [
            f"1. Query Intent: User asks: \"{user_q[:80]}\" (Domain: {topic}).",
            "2. Grounding Check: Reconcile all financial figures directly against verified deterministic calculations.",
            "3. Institutional Persona: Deliver direct boardroom CFO response with grounded figures and actionable advice.",
        ]

    thought_block = "<think>\n" + "\n".join(steps) + "\n</think>\n\n"
    new_msgs = [dict(m) for m in msgs]
    new_msgs[-1]["content"] = thought_block + last_content
    new_row = dict(row)
    new_row["messages"] = new_msgs
    return new_row


def build_and_export_tools_dataset(output_dir: str, rng: random.Random, count: int = 250, with_cot: bool = True) -> int:
    """Generates dataset/tools_train.jsonl with realistic function-calling trajectories."""
    tools_rows = []
    sys_prompt = (
        "You are the Autonomous SME Finance Copilot. You have access to deterministic financial calculation tools. "
        "Whenever a calculation or financial analysis is required, invoke the matching function with exact parameters. "
        "Never approximate figures or guess calculations."
    )

    for i in range(count):
        choice = rng.choice(["dscr", "dupont", "altman", "break_even", "trade_credit", "stage", "cash_flow"])
        call_id = f"call_{i+1:04d}"

        if choice == "dscr":
            noi = rng.randrange(50000, 500000, 10000)
            ds = rng.randrange(25000, int(noi * 0.85), 5000)
            dscr_dec = (Decimal(noi) / Decimal(ds)).quantize(Decimal("0.01"))
            status = "PRIME" if dscr_dec >= Decimal("1.35") else "APPROVED" if dscr_dec >= Decimal("1.25") else "CONDITIONAL"
            headroom = (dscr_dec - Decimal("1.25")).quantize(Decimal("0.01"))
            q = f"Calculate our Debt Service Coverage Ratio (DSCR) for net operating income of ${noi:,} and annual debt service of ${ds:,}."
            call = {"id": call_id, "type": "function", "function": {"name": "calculate_dscr", "arguments": {"net_operating_income": noi, "total_debt_service": ds}}}
            tool_resp = json.dumps({"dscr": float(dscr_dec), "status": status, "covenant_headroom": float(headroom), "noi": noi, "debt_service": ds})
            call_thought = f"<think>\nUser requests DSCR analysis for ${noi:,} NOI and ${ds:,} annual debt service. Invoke calculate_dscr to compute deterministic coverage ratio and covenant headroom.\n</think>"
            ans_thought = f"<think>\nTool calculate_dscr returned DSCR={dscr_dec}x, status={status}, and covenant headroom={headroom}x. Synthesize institutional advisory on debt service capacity.\n</think>\n\n"
            ans = (
                f"Your Debt Service Coverage Ratio is {dscr_dec}x with ${noi:,.2f} of NOI against ${ds:,.2f} of annual debt payments. "
                f"Lenders classify this coverage as {status.lower()} with {headroom}x of headroom above standard 1.25x bank covenants. "
                "Keep operating income steady through any financing application."
            )

        elif choice == "dupont":
            rev = rng.randrange(300000, 2000000, 50000)
            ni = rng.randrange(int(rev * 0.05), int(rev * 0.18), 5000)
            assets = rng.randrange(int(rev * 0.6), int(rev * 1.4), 25000)
            equity = rng.randrange(int(assets * 0.35), int(assets * 0.75), 25000)
            npm = (Decimal(ni) / Decimal(rev) * 100).quantize(Decimal("0.01"))
            at = (Decimal(rev) / Decimal(assets)).quantize(Decimal("0.01"))
            em = (Decimal(assets) / Decimal(equity)).quantize(Decimal("0.01"))
            roe = (Decimal(ni) / Decimal(equity) * 100).quantize(Decimal("0.01"))
            q = f"Run a 3-stage DuPont ROE breakdown: net income ${ni:,}, gross revenue ${rev:,}, assets ${assets:,}, equity ${equity:,}."
            call = {"id": call_id, "type": "function", "function": {"name": "calculate_dupont_roe", "arguments": {"net_income": ni, "revenue": rev, "total_assets": assets, "total_equity": equity}}}
            tool_resp = json.dumps({"roe_percent": float(roe), "net_profit_margin_percent": float(npm), "asset_turnover": float(at), "equity_multiplier": float(em)})
            call_thought = f"<think>\nUser requests 3-stage DuPont ROE breakdown. Invoke calculate_dupont_roe with revenue ${rev:,}, net income ${ni:,}, assets ${assets:,}, and equity ${equity:,}.\n</think>"
            ans_thought = f"<think>\nTool calculate_dupont_roe returned ROE={roe}%, net margin={npm}%, asset turnover={at}x, equity multiplier={em}x. Formulate quality-of-earnings advisory.\n</think>\n\n"
            ans = (
                f"Your aggregate Return on Equity is {roe}%, decomposed into a {npm}% net profit margin, {at}x asset turnover, and a {em}x equity multiplier. "
                f"Operating margin and asset velocity are the main drivers of this return, indicating high-quality earnings without excessive leverage. "
                "Maintain this margin profile while scaling customer acquisitions."
            )

        elif choice == "altman":
            assets = rng.randrange(200000, 1200000, 25000)
            wc = rng.randrange(int(assets * 0.05), int(assets * 0.25), 10000)
            re_val = rng.randrange(int(assets * 0.05), int(assets * 0.30), 10000)
            ebit = rng.randrange(int(assets * 0.05), int(assets * 0.20), 5000)
            bve = rng.randrange(int(assets * 0.25), int(assets * 0.55), 10000)
            tl = assets - bve
            sales = int(assets * 1.1)
            from services.calculations.credit_distress import calculate_altman_z_score
            z_res = calculate_altman_z_score(
                working_capital=Decimal(wc), retained_earnings=Decimal(re_val),
                ebit=Decimal(ebit), book_value_equity=Decimal(bve), total_liabilities=Decimal(tl),
                revenue=Decimal(sales), total_assets=Decimal(assets),
            )
            z_val = f"{z_res['altman_z_score']}"
            zone = z_res["distress_zone"]
            q = f"Calculate our Altman Z'-Score with working capital ${wc:,}, retained earnings ${re_val:,}, EBIT ${ebit:,}, equity ${bve:,}, liabilities ${tl:,}, revenue ${sales:,}, and assets ${assets:,}."
            call = {"id": call_id, "type": "function", "function": {"name": "calculate_altman_z_score", "arguments": {"working_capital": wc, "retained_earnings": re_val, "ebit": ebit, "book_value_equity": bve, "total_liabilities": tl, "revenue": sales, "total_assets": assets}}}
            tool_resp = json.dumps({"z_score": float(z_val), "zone": zone})
            call_thought = f"<think>\nUser requests Altman Z'-Score distress assessment. Invoke calculate_altman_z_score with working capital, retained earnings, EBIT, equity, liabilities, sales, and total assets.\n</think>"
            ans_thought = f"<think>\nTool calculate_altman_z_score returned Z'-score={z_val} in {zone} zone. Synthesize insolvency risk commentary and liquidity recommendations.\n</think>\n\n"
            ans = (
                f"Your Altman Z'-score is {z_val}, placing the business in the {zone.lower()} for commercial credit distress. "
                f"This reflects ${wc:,.2f} of working capital and ${ebit:,.2f} in operating earnings against ${tl:,.2f} of liabilities. "
                "Monitor short-term obligations and shore up liquid working capital before seeking new debt."
            )

        elif choice == "break_even":
            fc = rng.randrange(20000, 150000, 5000)
            margin = rng.choice([25, 30, 35, 40, 50])
            be = (Decimal(fc) / (Decimal(margin) / Decimal("100"))).quantize(Decimal("0.01"))
            q = f"What is our break-even revenue requirement if fixed operating costs are ${fc:,} and margin is {margin}%?"
            call = {"id": call_id, "type": "function", "function": {"name": "calculate_break_even", "arguments": {"fixed_costs": fc, "contribution_margin_ratio": margin}}}
            tool_resp = json.dumps({"break_even_revenue": float(be), "fixed_costs": fc, "contribution_margin_ratio": margin})
            call_thought = f"<think>\nUser requests break-even revenue requirement. Invoke calculate_break_even with fixed overhead ${fc:,} and margin {margin}%.\n</think>"
            ans_thought = f"<think>\nTool calculate_break_even returned break-even sales requirement of ${be:,.2f}. Synthesize target volume and operating margin advice.\n</think>\n\n"
            ans = (
                f"Your break-even revenue requirement is ${be:,.2f} based on ${fc:,.2f} in fixed overhead at a {margin}% contribution margin. "
                "Sales volume above this threshold yields operating profit, while falling short creates deficits. "
                "Track monthly revenues against that threshold and cut fixed costs if you keep falling short."
            )

        elif choice == "trade_credit":
            inv_val = rng.randrange(15000, 100000, 5000)
            disc, disc_days, net_days = rng.choice([(2, 10, 30), (1, 10, 30), (2, 10, 45)])
            days_fin = net_days - disc_days
            implied_apr = ((Decimal(disc) / (Decimal("100") - Decimal(disc))) * (Decimal("365") / Decimal(days_fin)) * Decimal("100")).quantize(Decimal("0.01"))
            savings = (Decimal(inv_val) * (Decimal(disc) / Decimal("100"))).quantize(Decimal("0.01"))
            q = f"Evaluate trade terms {disc}/{disc_days} net {net_days} on a ${inv_val:,} supplier invoice."
            call = {"id": call_id, "type": "function", "function": {"name": "calculate_trade_credit_apr", "arguments": {"discount_pct": disc, "discount_days": disc_days, "net_days": net_days, "invoice_amount": inv_val}}}
            tool_resp = json.dumps({"implied_apr_percent": float(implied_apr), "discount_dollar_savings": float(savings), "days_financed": days_fin})
            call_thought = f"<think>\nUser requests trade credit discount evaluation for {disc}/{disc_days} net {net_days}. Invoke calculate_trade_credit_apr on ${inv_val:,} invoice.\n</think>"
            ans_thought = f"<think>\nTool calculate_trade_credit_apr returned implied APR of {implied_apr}% and ${savings:,.2f} savings. Provide commercial credit comparison advisory.\n</think>\n\n"
            ans = (
                f"Skipping the {disc}% discount on your ${inv_val:,.2f} invoice costs an implied annualized APR of {implied_apr}%, sacrificing ${savings:,.2f} in discount savings. "
                f"That rate is far higher than standard commercial credit lines. "
                f"Pay the supplier by day {disc_days} and draw on a lower-rate credit line if cash is tight."
            )

        elif choice == "stage":
            amt = rng.randrange(20000, 100000, 5000)
            apr = rng.choice([7.5, 8.5, 9.5, 10.5, 12.0])
            fac = rng.choice(["Working Capital Line", "Invoice Factoring Facility", "Revolving Credit Line"])
            q = f"Please stage a ${amt:,} proposal for the {fac} at {apr}% APR."
            call = {"id": call_id, "type": "function", "function": {"name": "stage_financing_intent", "arguments": {"facility_name": fac, "amount": amt, "apr_percent": apr}}}
            tool_resp = json.dumps({"status": "STAGED", "tier": 2, "facility_name": fac, "amount": amt, "apr_percent": apr, "sent_by": "owner"})
            call_thought = f"<think>\nUser requests staging a ${amt:,} financing proposal for {fac} at {apr}% APR. Invoke stage_financing_intent to write proposal into Tier 2 staging ledger.\n</think>"
            ans_thought = f"<think>\nTool stage_financing_intent successfully staged proposal with Tier 2 isolation. Advise user of terms and remind that nothing is sent until they send the request themselves.\n</think>\n\n"
            ans = (
                f"I have staged the ${amt:,.2f} {fac} proposal at {apr}% APR into the Tier 2 staging ledger. "
                "No funds have moved and no contract is finalized. "
                "Inspect the terms in Approvals and prepare the request when you are ready to send it."
            )

        else:  # cash_flow
            csv_snippet = "Date,Description,Amount,Balance\\n2026-03-01,Client Inflow,15000.00,45000.00\\n2026-03-05,Payroll,-8000.00,37000.00"
            bal = rng.randrange(25000, 150000, 5000)
            burn = rng.randrange(800, 3000, 100)
            runway = int(bal / burn)
            q = "What is our current cash balance and runway based on the uploaded transactions?"
            call = {"id": call_id, "type": "function", "function": {"name": "tool_analyze_cash_flow", "arguments": {"csv_content": csv_snippet}}}
            tool_resp = json.dumps({"current_balance": f"{bal:.2f}", "average_daily_burn": f"{burn:.2f}", "runway_days": runway, "has_projected_deficit": False})
            call_thought = f"<think>\nUser requests cash balance and runway analysis from uploaded statement. Invoke tool_analyze_cash_flow on transaction CSV data.\n</think>"
            ans_thought = f"<think>\nTool tool_analyze_cash_flow returned balance ${bal:,}, daily burn ${burn:,}, and {runway}-day runway without deficit. Formulate liquidity monitoring advice.\n</think>\n\n"
            ans = (
                f"Your verified current balance is ${bal:,.2f} with an average daily burn of ${burn:,.2f}/day, yielding an estimated {runway}-day runway. "
                "Inflows currently support ongoing operational disbursements without an immediate deficit. "
                "Monitor customer receipt timing closely to ensure cash reserves remain above zero."
            )

        msgs = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": q},
            {"role": "assistant", "content": call_thought if with_cot else "", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": call_id, "name": call["function"]["name"], "content": tool_resp},
            {"role": "assistant", "content": (ans_thought if with_cot else "") + ans},
        ]
        tools_rows.append({"messages": msgs, "tools": TOOLS_SCHEMA})

    tools_file = os.path.join(output_dir, "tools_train.jsonl")
    os.makedirs(output_dir, exist_ok=True)
    with open(tools_file, "w", encoding="utf-8") as f:
        for r in tools_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(tools_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cash-statements", type=int, default=900, help="statements for cash rows (2 rows each)")
    parser.add_argument("--underwriting-statements", type=int, default=500)
    parser.add_argument("--quant-per-intent", type=int, default=60)
    parser.add_argument("--concept-cards", type=int, default=550)
    parser.add_argument("--multiturn", type=int, default=1600)
    parser.add_argument("--conversational", type=int, default=250)
    parser.add_argument("--refusals", type=int, default=100)
    parser.add_argument("--governance", type=int, default=80)
    parser.add_argument("--scenarios", type=int, default=240)
    parser.add_argument("--bridge-plans", type=int, default=150)
    parser.add_argument("--outflow-breakdown", type=int, default=120)
    parser.add_argument("--receivables-ageing", type=int, default=120)
    parser.add_argument("--missing-statement", type=int, default=120)
    parser.add_argument("--volatility", type=int, default=100, help="statements for weekly revenue volatility rows")
    parser.add_argument("--with-cot", action="store_true", default=True, help="Format structured chain-of-thought verification inside <think> tags")
    parser.add_argument("--no-cot", dest="with_cot", action="store_false", help="Disable chain-of-thought verification")
    parser.add_argument("--export-tools", action="store_true", help="Generate dataset/tools_train.jsonl with typed function calling trajectories")
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    builders: List[tuple] = [
        ("cash diagnostic", lambda: build_cash_rows(rng, args.cash_statements)),
        ("credit underwriting", lambda: build_underwriting_rows(rng, args.underwriting_statements)),
        ("quantitative calculations", lambda: build_quant_rows(rng, args.quant_per_intent)),
        ("revenue volatility", lambda: build_revenue_volatility_rows(rng, args.volatility)),
        ("what-if scenarios", lambda: build_scenario_rows(rng, args.scenarios)),
        ("bridge plans", lambda: build_bridge_rows(rng, args.bridge_plans)),
        ("outflow breakdown", lambda: build_outflow_breakdown_rows(rng, args.outflow_breakdown)),
        ("receivables ageing", lambda: build_receivables_ageing_rows(rng, args.receivables_ageing)),
        ("concept knowledge", lambda: build_concept_card_rows(rng, args.concept_cards)),
        ("multiturn follow-up", lambda: build_multiturn_rows(rng, args.multiturn)),
        ("conversational", lambda: build_conversational_rows(rng, args.conversational)),
        ("off-topic refusals", lambda: build_refusal_rows(rng, args.refusals)),
        ("tier3 governance", lambda: build_governance_rows(rng, args.governance)),
        ("missing statement", lambda: build_missing_statement_rows(rng, args.missing_statement)),
    ]
    candidates: List[Dict[str, Any]] = []
    for label, build in builders:
        made = build()
        print(f"  {label:28s} {len(made):5d} candidate rows", flush=True)
        candidates.extend(made)

    if args.with_cot:
        candidates = [add_cot_thought(r, rng) for r in candidates]

    rejections: Counter = Counter()
    filtered = []
    for row in candidates:
        reason = rejection_reason(row)
        if reason:
            rejections[reason] += 1
        else:
            filtered.append(row)

    # Question uniqueness filter: preserve distinct questions across candidates
    seen_questions: set[str] = set()
    kept = []
    for row in filtered:
        q_norm = row["messages"][-2]["content"].strip().lower()
        kind = row["_kind"].split(":")[0]
        # For conversational and refusals, allow modest reuse; for quant/cash/concept require uniqueness
        if kind in ("conversational", "refusal", "governance", "missing", "bridge", "outflow", "receivables"):
            kept.append(row)
        elif kind == "multiturn":
            t1_q = row["messages"][1]["content"].strip().lower() if len(row["messages"]) >= 4 else ""
            mt_key = f"{t1_q} || {q_norm}"
            if mt_key not in seen_questions:
                seen_questions.add(mt_key)
                kept.append(row)
            elif rng.random() < 0.05:
                kept.append(row)
        elif q_norm not in seen_questions:
            seen_questions.add(q_norm)
            kept.append(row)
        elif rng.random() < 0.05:  # Allow max 5% repeat across different statements
            kept.append(row)

    # Exact repeats survive the reuse allowances above; drop them so no conversation lands in both train and val.
    seen_convos: set[str] = set()
    unique = []
    for row in kept:
        key = json.dumps([m["content"] for m in row["messages"][1:]])
        if key not in seen_convos:
            seen_convos.add(key)
            unique.append(row)
    kept = unique

    engine_rows = [r for r in kept if r["_base_reply"]]
    grounded = sum(
        1 for r in engine_rows
        if numbers_are_grounded(
            extract_prose(r["messages"][-1]["content"]),
            r["_base_reply"],
            context="\n".join(f"{m['role']}: {m['content']}" for m in r["messages"][:-1]),
        )
    )

    multiturn_kept = [r for r in kept if len(r["messages"]) > 3]
    singleturn_kept = [r for r in kept if len(r["messages"]) <= 3]
    mt_val_size = len(multiturn_kept) // 10
    st_val_size = len(singleturn_kept) // 10

    train_data = multiturn_kept[mt_val_size:] + singleturn_kept[st_val_size:]
    val_data = multiturn_kept[:mt_val_size] + singleturn_kept[:st_val_size]
    for _attempt in range(100):
        rng.shuffle(multiturn_kept)
        rng.shuffle(singleturn_kept)
        cand_val = multiturn_kept[:mt_val_size] + singleturn_kept[:st_val_size]
        cand_train = multiturn_kept[mt_val_size:] + singleturn_kept[st_val_size:]
        rng.shuffle(cand_val)
        rng.shuffle(cand_train)
        val_top = Counter(skeleton(r["messages"][-1]["content"]) for r in cand_val).most_common(1)[0][1] / len(cand_val)
        train_top = Counter(skeleton(r["messages"][-1]["content"]) for r in cand_train).most_common(1)[0][1] / len(cand_train)
        if val_top <= 0.02 and train_top <= 0.02:
            train_data, val_data = cand_train, cand_val
            break

    splits = {"finetune_train.jsonl": train_data, "finetune_val.jsonl": val_data}
    os.makedirs(args.output_dir, exist_ok=True)
    for name, data in splits.items():
        with open(os.path.join(args.output_dir, name), "w", encoding="utf-8") as fh:
            for row in data:
                fh.write(json.dumps({"messages": row["messages"]}, ensure_ascii=False) + "\n")

    replies = [r["messages"][-1]["content"] for r in kept]
    questions = [r["messages"][-2]["content"].strip().lower() for r in kept]
    openers = Counter(opening(r) for r in replies)
    skeletons = Counter(skeleton(r) for r in replies)
    kinds = Counter(r["_kind"].split(":")[0] for r in kept)
    unique_q_pct = len(set(questions)) / max(1, len(questions)) * 100.0

    print("=" * 70)
    print(f"Kept {len(kept)} of {len(candidates)} rows ({dict(rejections) or 'no rejections'})")
    print(f"Grounding pass rate (engine rows): {grounded}/{len(engine_rows)} = {grounded / max(1, len(engine_rows)):.1%}")
    print(f"Unique questions rate: {len(set(questions))}/{len(questions)} ({unique_q_pct:.1f}%)")
    print(f"Row mix: {dict(kinds)}")
    print(f"Top 10 opening phrases cover {sum(c for _, c in openers.most_common(10)) / len(replies):.1%} of replies")
    print(f"Largest reply skeleton: {skeletons.most_common(1)[0][1] / len(replies):.2%} of replies")
    for name, data in splits.items():
        print(f"Wrote {len(data)} rows to {os.path.join(args.output_dir, name)}")

    if args.export_tools:
        tools_count = build_and_export_tools_dataset(args.output_dir, rng, with_cot=args.with_cot)
        print(f"Wrote {tools_count} tool-calling rows to {os.path.join(args.output_dir, 'tools_train.jsonl')}")


if __name__ == "__main__":
    main()

