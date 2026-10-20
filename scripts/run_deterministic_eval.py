"""Deterministic Evaluation Suite Runner for SME Finance Copilot.

Executes all 5 deterministic evaluation pillars:
1. Semantic Routing & Follow-Up Intent Classification (FastEmbed ONNX)
2. Pure Decimal FinTech Mathematics (DAB, CCC, DSCR, APR, Z'-score, DuPont)
3. Policy Decision Tables (ZenEngine Covenants, Usury Limits, Risk Policies)
4. Security Invariants, Session Isolation & Owner-Sent Tier 3 Governance
5. Held-Out 100-Sample Gold-Standard Benchmark (Grounding, Anti-Slop, Refusal)

Outputs a consolidated, audited evaluation scorecard.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import pytest
from scripts.eval_model import DEFAULT_EVAL_FILE, run_evaluation


class TestCollectorPlugin:
    """Lightweight pytest plugin to capture exact pass/fail counts per pillar."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.total = 0

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            self.total += 1
            if report.passed:
                self.passed += 1
            elif report.failed:
                self.failed += 1
            elif report.skipped:
                self.skipped += 1


def run_pytest_suite(name: str, targets: List[str]) -> Dict[str, Any]:
    """Runs pytest on targeted test paths and returns structured metrics."""
    collector = TestCollectorPlugin()
    t0 = time.time()
    exit_code = pytest.main(["-q", "--no-header", *targets], plugins=[collector])
    elapsed = time.time() - t0

    return {
        "pillar": name,
        "targets": targets,
        "total": collector.total,
        "passed": collector.passed,
        "failed": collector.failed,
        "skipped": collector.skipped,
        "exit_code": int(exit_code),
        "elapsed_seconds": round(elapsed, 2),
        "pass_rate_pct": round((collector.passed / max(1, collector.total)) * 100, 1),
    }


def execute_deterministic_eval(output_json: str | None = None) -> Dict[str, Any]:
    """Executes all 5 pillars of the deterministic evaluation suite."""
    print("=" * 80)
    print("SME FINANCE COPILOT — RUNNING DETERMINISTIC EVALUATION SUITE")
    print("=" * 80)

    pillars = [
        (
            "Pillar 1: Semantic Intent & Follow-up Routing",
            ["tests/unit/test_concept_routing.py"],
        ),
        (
            "Pillar 2: Pure Decimal FinTech Math Precision",
            [
                "tests/unit/test_calculations.py",
                "tests/unit/test_predictive_cash.py",
                "tests/unit/test_solvency_and_trade_credit.py",
                "tests/unit/test_treasury_dupont_lease.py",
                "tests/unit/test_currency_calculations.py",
                "tests/unit/test_cash_analysis.py",
                "tests/unit/test_financial_metrics.py",
                "tests/unit/test_cash_scenario.py",
                "tests/unit/test_outflow_breakdown.py",
                "tests/unit/test_receivables_ageing.py",
                "tests/unit/test_portfolio_consolidator.py",
                "tests/unit/test_invoice_parser.py",
                "tests/unit/test_enterprise_finance_tools.py",
            ],
        ),
        (
            "Pillar 3: Policy Decision Tables (ZenEngine)",
            [
                "tests/unit/test_decision_engine.py",
                "tests/unit/test_csv_decision_engine.py",
                "tests/unit/test_pdf_decision_policies.py",
                "tests/integration/test_decision_api.py",
            ],
        ),
        (
            "Pillar 4: Security, Isolation & Owner-Sent Governance",
            [
                "tests/security/test_invariants.py",
                "tests/unit/test_security_gate.py",
                "tests/unit/test_session_store.py",
            ],
        ),
    ]

    pillar_results = []
    total_passed = 0
    total_tests = 0
    all_success = True

    for name, targets in pillars:
        print(f"\n[EVAL] Running {name}...")
        res = run_pytest_suite(name, targets)
        pillar_results.append(res)
        total_passed += res["passed"]
        total_tests += res["total"]
        if res["failed"] > 0 or res["exit_code"] != 0:
            all_success = False
        print(f"       -> {res['passed']}/{res['total']} passed in {res['elapsed_seconds']}s ({res['pass_rate_pct']}%)")

    # Pillar 5: Held-Out 100-Case Benchmark
    print(f"\n[EVAL] Running Pillar 5: Held-Out 100-Case Benchmark (Grounding & Anti-Slop)...")
    t0 = time.time()
    bm_res = run_evaluation(DEFAULT_EVAL_FILE, use_mock=True)
    bm_elapsed = round(time.time() - t0, 2)
    bm_passed = bm_res["passed"]
    bm_total = bm_res["total"]
    bm_pct = bm_res["pass_rate_pct"]
    total_passed += bm_passed
    total_tests += bm_total

    pillar_results.append({
        "pillar": "Pillar 5: Held-Out 100-Case Benchmark",
        "targets": ["dataset/eval_set.jsonl"],
        "total": bm_total,
        "passed": bm_passed,
        "failed": bm_total - bm_passed,
        "skipped": 0,
        "exit_code": 0 if bm_passed == bm_total else 1,
        "elapsed_seconds": bm_elapsed,
        "pass_rate_pct": bm_pct,
    })
    print(f"       -> {bm_passed}/{bm_total} passed in {bm_elapsed}s ({bm_pct}%)")

    overall_pass_pct = round((total_passed / max(1, total_tests)) * 100, 1)

    # Render Scorecard Matrix
    print("\n" + "=" * 80)
    print("SME FINANCE COPILOT — DETERMINISTIC EVALUATION SCORECARD")
    print("=" * 80)
    print(f"{'Evaluation Pillar':50s} | {'Passed':7s} | {'Total':6s} | {'Rate':8s} | {'Status':8s}")
    print("-" * 80)
    for p in pillar_results:
        status = "PASSED" if p["failed"] == 0 and p["exit_code"] == 0 else "FAILED"
        print(f"{p['pillar']:50s} | {p['passed']:7d} | {p['total']:6d} | {p['pass_rate_pct']:6.1f}% | {status:8s}")
    print("=" * 80)
    print(f"CONSOLIDATED AUDITED METRIC: {total_passed}/{total_tests} passed ({overall_pass_pct}%)\n")

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_status": "PASSED" if all_success and bm_passed == bm_total else "FAILED",
        "total_assertions": total_tests,
        "total_passed": total_passed,
        "overall_pass_rate_pct": overall_pass_pct,
        "pillars": pillar_results,
        "held_out_benchmark_breakdown": bm_res.get("suite_breakdown", {}),
    }

    if output_json:
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Detailed scorecard written to: {output_json}\n")

    return report


def main():
    parser = argparse.ArgumentParser(description="Run SME Finance Copilot Deterministic Evaluation Suite.")
    parser.add_argument("--output_json", type=str, default=None, help="Path to write JSON evaluation scorecard.")
    args = parser.parse_args()

    report = execute_deterministic_eval(output_json=args.output_json)
    if report["overall_status"] != "PASSED":
        sys.exit(1)


if __name__ == "__main__":
    main()
