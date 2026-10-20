"""Dataset health audit for the LoRA fine-tune (dataset/finetune_*.jsonl).

Checks that every row matches the runtime call shape and the reply contract:
1. Exactly system, user, assistant turns; no tool turns or tool calls (the local engine never passes tools).
2. Token length under 2048 with the base model's chat template.
3. No <thought> blocks, '###' headers or metric bullets in replies (sanitize_cfo_reply deletes them).
4. Every reply passes numbers_are_grounded() against the engine output embedded in its system prompt.
5. Reply variety: no single reply skeleton (figures masked) above 2% of rows.
"""

import json
import os
import re
import sys
from collections import Counter

from transformers import AutoTokenizer

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from services.agent.prompts import numbers_are_grounded

TRAIN_PATH = "dataset/finetune_train.jsonl"
VAL_PATH = "dataset/finetune_val.jsonl"
from services.agent.local_transformers import BASE_MODEL_ID, base_on_disk
TOKENIZER_DIR = base_on_disk(BASE_MODEL_ID) or BASE_MODEL_ID
MAX_TOKENS = 2048
MAX_SKELETON_SHARE = 0.02

# The CASH_DIAGNOSTIC and CREDIT_UNDERWRITING templates in agent_persona_policy.json wrap base_reply in these markers.
BASE_REPLY_PATTERN = re.compile(
    r"(?:Verified Financial Engine Outputs|Verified Underwriting Dossier):\n(.*?)\n\n(?:Executive|Underwriting) Advisory Guidelines",
    re.DOTALL,
)
METRIC_BULLET = re.compile(r"(?m)^\s*[-*•]\s")


def extract_prose(reply: str) -> str:
    if "<think>" in reply:
        m = re.search(r"<think>(.*?)</think>\s*", reply, re.DOTALL)
        if m:
            return reply[m.end():].strip()
    return reply


def skeleton(reply: str) -> str:
    return re.sub(r"\d[\d,]*(?:\.\d+)?", "#", extract_prose(reply))


def opening(reply: str) -> str:
    return " ".join(re.sub(r"[*$]", "", extract_prose(reply)).lower().split()[:3])


def is_valid_roles(roles: list) -> bool:
    if len(roles) < 3 or len(roles) % 2 != 1:
        return False
    if roles[0] != "system":
        return False
    for i in range(1, len(roles), 2):
        if roles[i] != "user" or roles[i + 1] != "assistant":
            return False
    return True


EVAL_PATH = "dataset/eval_set.jsonl"


def load_eval_questions() -> set[str]:
    if not os.path.exists(EVAL_PATH):
        return set()
    questions = set()
    with open(EVAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            msgs = rec.get("messages", [])
            for m in reversed(msgs):
                if m.get("role") == "user":
                    questions.add(m.get("content", "").strip().lower())
                    break
    return questions


ROUTINE_KEYWORDS = {
    "Altman Z'-Score": ["altman", "z'-score", "z-score", "distress zone"],
    "DuPont 3-Stage ROE": ["dupont", "return on equity", "asset turnover", "equity multiplier"],
    "Debt Service Coverage (DSCR)": ["dscr", "debt service coverage"],
    "Discounted Cash Flow (DCF)": ["dcf", "discounted cash flow", "terminal value", "wacc"],
    "Weekly Revenue Volatility": ["volatility", "inflow volatility", "weekly revenue"],
    "Working Capital (WCR/DSO)": ["working capital", "wcr", "days sales outstanding", "dso"],
    "Break-Even Analysis": ["break-even", "contribution margin"],
    "Trade Credit (APR)": ["trade credit", "early payment discount", "implied apr"],
    "Cash Runway & Burn": ["runway", "daily burn", "overdraft", "deficit"],
    "Credit Underwriting": ["underwriting", "facility", "factoring", "credit line"],
    "Defensive Interval (DIR)": ["defensive interval", "quick assets"],
}

TOOLS_PATH = "dataset/tools_train.jsonl"


def audit_file(filepath: str, tokenizer, eval_questions: set[str]) -> dict:
    stats = Counter()
    routine_counts = Counter()
    replies = []
    questions = []
    max_tokens = 0
    with open(filepath, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            stats["total"] += 1
            messages = json.loads(line).get("messages", [])
            roles = [m.get("role") for m in messages]
            if not is_valid_roles(roles):
                stats["bad_shape"] += 1
            if "tool" in roles or any(m.get("tool_calls") for m in messages):
                stats["tool_rows"] += 1
            if len(messages) < 3:
                continue

            system = messages[0].get("content") or ""
            user_msg = messages[-2].get("content") or ""
            reply = messages[-1].get("content") or ""

            # Check routine representation
            full_text = " ".join(m.get("content", "") or "" for m in messages).lower()
            for routine_name, kw_list in ROUTINE_KEYWORDS.items():
                if any(kw in full_text for kw in kw_list):
                    routine_counts[routine_name] += 1

            q_clean = user_msg.strip().lower()
            questions.append(q_clean)
            if q_clean in eval_questions:
                stats["eval_leakage"] += 1

            if len(messages) > 3:
                stats["multiturn_rows"] += 1
                base_reply = ""
            else:
                match = BASE_REPLY_PATTERN.search(system)
                base_reply = match.group(1) if match else ""
                if base_reply:
                    stats["engine_rows"] += 1

            replies.append(reply)
            prose_reply = reply
            if "<think>" in reply:
                stats["thought"] += 1
                m_think = re.search(r"<think>(.*?)</think>\s*", reply, re.DOTALL)
                if not m_think:
                    stats["unclosed_think"] += 1
                else:
                    prose_reply = reply[m_think.end():].strip()
            elif "<thought" in reply:
                stats["thought"] += 1

            if "###" in prose_reply or METRIC_BULLET.search(prose_reply):
                stats["headers_or_bullets"] += 1

            conv_context = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in messages[:-1])
            if numbers_are_grounded(prose_reply, base_reply, context=conv_context):
                stats["grounded"] += 1
            try:
                formatted = tokenizer.apply_chat_template(messages, tokenize=False)
                tok_len = len(tokenizer(formatted)["input_ids"])
                max_tokens = max(max_tokens, tok_len)
                if tok_len > MAX_TOKENS:
                    stats["over_limit"] += 1
            except Exception as e:
                print(f"Error tokenizing record {idx}: {e}")
                stats["over_limit"] += 1
    openers = Counter(opening(r) for r in replies)
    skeletons = Counter(skeleton(r) for r in replies)
    unique_q_rate = len(set(questions)) / max(1, len(questions))
    return {
        "file": filepath,
        "stats": stats,
        "max_tokens": max_tokens,
        "unique_q_rate": unique_q_rate,
        "routine_counts": routine_counts,
        "top10_opener_share": sum(c for _, c in openers.most_common(10)) / max(1, len(replies)),
        "top_skeleton_share": skeletons.most_common(1)[0][1] / max(1, len(replies)) if replies else 0.0,
    }


def audit_tools_file(filepath: str, tokenizer) -> dict:
    if not os.path.exists(filepath):
        return {"exists": False}
    stats = Counter()
    with open(filepath, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            stats["total"] += 1
            data = json.loads(line)
            tools = data.get("tools", [])
            messages = data.get("messages", [])
            if not tools or not isinstance(tools, list):
                stats["invalid_tools_schema"] += 1
            if len(messages) < 4:
                stats["invalid_message_length"] += 1
            has_call = any(m.get("tool_calls") for m in messages)
            has_tool_resp = any(m.get("role") == "tool" for m in messages)
            if not (has_call and has_tool_resp):
                stats["missing_tool_call_flow"] += 1
            try:
                tokenizer.apply_chat_template(messages, tools=tools, tokenize=False)
            except Exception as exc:
                stats["template_render_error"] += 1
    return {"exists": True, "file": filepath, "stats": stats}


def main():
    print("Loading tokenizer from:", TOKENIZER_DIR)
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_DIR, trust_remote_code=True)
    eval_questions = load_eval_questions()
    print(f"Loaded {len(eval_questions)} held-out evaluation questions for contamination check.")

    results = [audit_file(path, tokenizer, eval_questions) for path in (TRAIN_PATH, VAL_PATH)]

    print("=" * 65)
    print("DATASET HEALTH REPORT")
    print("=" * 65)
    for r in results:
        s = r["stats"]
        print(f"File: {r['file']}")
        print(f"  - Total Records:          {s['total']}")
        print(f"  - Multi-Turn Records:     {s['multiturn_rows']} ({s['multiturn_rows'] / max(1, s['total']):.1%})")
        print(f"  - Unique Questions Rate:  {r['unique_q_rate']:.1%}")
        print(f"  - Eval Set Contamination: {s['eval_leakage']}")
        print(f"  - Max Token Length:       {r['max_tokens']} (Limit: {MAX_TOKENS})")
        print(f"  - Over Limit:             {s['over_limit']}")
        print(f"  - Invalid Role Shape:     {s['bad_shape']}")
        print(f"  - Rows With Tool Turns:   {s['tool_rows']} ({s['tool_rows'] / max(1, s['total']):.1%})")
        print(f"  - <thought>/<think> Tags: {s['thought']} (Unclosed: {s['unclosed_think']})")
        print(f"  - Headers/Bullets:        {s['headers_or_bullets']}")
        print(f"  - Grounded Replies:       {s['grounded']}/{s['total']} ({s['engine_rows']} carry engine output)")
        print(f"  - Top 10 Opener Share:    {r['top10_opener_share']:.1%}")
        print(f"  - Largest Skeleton Share: {r['top_skeleton_share']:.2%}")
        print("  - Deterministic Routine Coverage:")
        for r_name, r_cnt in r["routine_counts"].most_common():
            print(f"      * {r_name:32s}: {r_cnt:4d} samples ({r_cnt / max(1, s['total']):.1%})")
        print("-" * 65)

    # Tool calling dataset audit
    tool_audit = audit_tools_file(TOOLS_PATH, tokenizer)
    if tool_audit.get("exists"):
        ts = tool_audit["stats"]
        print(f"File: {tool_audit['file']} (Tool Calling Dataset)")
        print(f"  - Total Tool-Calling Records: {ts['total']}")
        print(f"  - Invalid Tool Schemas:       {ts['invalid_tools_schema']}")
        print(f"  - Broken Call/Response Flows: {ts['missing_tool_call_flow']}")
        print(f"  - Template Render Errors:     {ts['template_render_error']}")
        assert ts["total"] > 0, "tools_train.jsonl is empty"
        assert ts["invalid_tools_schema"] == 0, "Invalid tool schema in tools_train.jsonl"
        assert ts["missing_tool_call_flow"] == 0, "Missing tool call flow in tools_train.jsonl"
        assert ts["template_render_error"] == 0, "Template rendering failed on tool-calling dataset"
        print("-" * 65)

    for r in results:
        s, name = r["stats"], r["file"]
        assert s["total"] > 0, f"{name} is empty"
        assert s["over_limit"] == 0, f"{name}: records exceed {MAX_TOKENS} tokens"
        assert s["bad_shape"] == 0, f"{name}: records have invalid role structure"
        assert s["tool_rows"] == 0, f"{name}: records contain tool turns the runtime never sends"
        if s["thought"] > 0:
            assert s["unclosed_think"] == 0, f"{name}: contains unclosed <think> blocks"
        assert s["headers_or_bullets"] == 0, f"{name}: replies contain headers or metric bullets"
        assert s["grounded"] == s["total"], f"{name}: replies fail numbers_are_grounded"
        assert s["eval_leakage"] == 0, f"{name}: {s['eval_leakage']} questions overlap with held-out eval set!"
        assert r["top_skeleton_share"] <= MAX_SKELETON_SHARE, f"{name}: one reply skeleton exceeds {MAX_SKELETON_SHARE:.0%}"
        if "train" in name:
            mt_share = s["multiturn_rows"] / max(1, s["total"])
            assert mt_share >= 0.20, f"{name}: multi-turn share {mt_share:.1%} is below 20% target"
    print("STATUS: PASS. All records match the runtime prompt shape, multi-turn balance, and reply contract.")


if __name__ == "__main__":
    main()
