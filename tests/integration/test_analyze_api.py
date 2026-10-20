from fastapi.testclient import TestClient

from api.main import app
from api.routes import analyze

client = TestClient(app)
CSV = (
    "transaction_id,posted_on,amount,currency,description,closing_balance\n"
    "tx-1,2026-10-01,-10.00,USD,Office supplies,90.00\n"
    "tx-2,2026-10-02,5.00,USD,Customer payment,95.00\n"
)


def test_analyze_api_returns_decimal_strings_and_row_provenance():
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "10", "as_of_date": "2026-10-02"},
        files={"file": ("synthetic.csv", CSV.encode(), "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "currency": "USD",
        "accepted_count": 2,
        "rejected_rows": [],
        "current_balance": "95.00",
        "net_period_change": "-5.00",
        "gross_inflows": "5.00",
        "gross_outflows": "10.00",
        "period_days": 2,
        "average_daily_burn": "2.50",
        "runway_days": 38,
        "alert_threshold_days": 10,
        "cash_status": "WATCH",
        "cash_conversion_cycle_days": None,
        "working_capital_status": None,
        "working_capital_rationale": None,
        "start_date": "2026-10-01",
        "end_date": "2026-10-02",
        "statement_age_days": 0,
        "analysis_mode": "LIVE_OPERATING",
        "projected_depletion_date": "2026-11-09",
        "alert_boundary_date": "2026-10-12",
        "accounts_breakdown": [
            {
                "file_name": "synthetic.csv",
                "account_id": "Account_1",
                "start_date": "2026-10-01",
                "end_date": "2026-10-02",
                "closing_balance": "95.00",
                "transaction_count": 2,
            }
        ],
        "internal_transfers_excluded": None,
        "internal_transfers": None,
        "calendar_gaps": None,
        "has_overlaps_deduped": None,
        "operational_inflows": "5.00",
        "operational_outflows": "10.00",
        "document_format": "CSV",
        "page_count": None,
        "normalized_csv": None,
        "balance_history": [{"date": "2026-10-01", "balance": "90.00"}, {"date": "2026-10-02", "balance": "95.00"}],
        "account_history": [
            {"account_id": "Account_1", "points": [{"date": "2026-10-01", "balance": "90.00"}, {"date": "2026-10-02", "balance": "95.00"}]}
        ],
        "recurring_obligations": [],
        # $95 at $2.50 a day lasts 38 days; day 39 is the first negative balance.
        "forecast": {
            "anchor_date": "2026-10-02",
            "has_projected_deficit": True,
            "severity": "WARNING",
            "days_until_deficit": 39,
            "projected_deficit_date": "2026-11-10",
            "projected_shortfall_amount": "2.50",
            "recommended_bridge_amount": "500.00",
            "primary_deficit_trigger": "OPERATING_BURN",
            "detected_recurring_payroll": None,
            "detected_recurring_rent": None,
            "detected_recurring_debt": None,
        },
        "projection": body["projection"],
    }
    assert len(body["projection"]) == 91
    assert body["projection"][0] == {"date": "2026-10-02", "balance": "95.00"}
    assert body["projection"][-1] == {"date": "2026-12-31", "balance": "-130.00"}


def test_analyze_api_with_cash_conversion_cycle():
    response = client.post(
        "/api/v1/analyze",
        data={
            "alert_threshold_days": "10",
            "dso_days": "45",
            "dpo_days": "15",
            "dio_days": "0",
        },
        files={"file": ("synthetic.csv", CSV.encode(), "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cash_conversion_cycle_days"] == 30
    assert body["working_capital_status"] == "BALANCED"
    assert "balanced at 30 days" in body["working_capital_rationale"]


def test_analyze_api_reports_file_errors_in_stable_shape():
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "10"},
        files={"file": ("invalid.csv", b"bad,header\n", "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_HEADER"


def test_analyze_api_rejects_invalid_threshold():
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "0"},
        files={"file": ("synthetic.csv", CSV.encode(), "text/csv")},
    )
    assert response.status_code == 422


def test_analyze_api_enforces_configured_upload_limit(monkeypatch):
    monkeypatch.setattr(analyze, "MAX_UPLOAD_BYTES", 8)
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "10"},
        files={"file": ("large.csv", CSV.encode(), "text/csv")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "UPLOAD_TOO_LARGE"


def test_analyze_api_defaults_threshold_to_30_when_omitted():
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("synthetic.csv", CSV.encode(), "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["alert_threshold_days"] == 30


def test_analyze_api_adapts_to_historical_audit_mode_for_outdated_statement():
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "10", "as_of_date": "2027-01-01"},
        files={"file": ("synthetic.csv", CSV.encode(), "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["statement_age_days"] == 91
    assert body["analysis_mode"] == "HISTORICAL_AUDIT"


def test_analyze_api_with_multiple_csv_files():
    file1 = (
        "Date,Description,Amount,Running Bal.\n"
        "2026-10-01,Invoice payment,1000.00,5000.00\n"
        "2026-10-02,Software subscription,-50.00,4950.00\n"
    ).encode()
    file2 = (
        "Date,Description,Amount,Running Bal.\n"
        "2026-10-03,Client retainer,2000.00,6950.00\n"
        "2026-10-04,Office supply,-150.00,6800.00\n"
    ).encode()

    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "15"},
        files=[
            ("files", ("oct_part1.csv", file1, "text/csv")),
            ("files", ("oct_part2.csv", file2, "text/csv")),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted_count"] == 4
    assert body["current_balance"] == "6800.00"
    assert body["period_days"] == 4


def test_analyze_api_with_universal_bofa_format():
    bofa_csv = (
        "Date,Description,Amount,Running Bal.\n"
        "10/01/2026,Deposit,3000.00,10000.00\n"
        "10/05/2026,Office Depot,-200.00,9800.00\n"
    ).encode()

    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "30"},
        files={"file": ("bofa_statement.csv", bofa_csv, "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted_count"] == 2
    assert body["current_balance"] == "9800.00"


def test_analyze_api_multi_account_portfolio_consolidation_and_contra_transfer():
    chase_csv = (
        "Date,Description,Amount,Running Bal.\n"
        "2026-10-01,Client Payment,5000.00,15000.00\n"
        "2026-10-02,Wire to SVB Checking,-2000.00,13000.00\n"
    ).encode()
    svb_csv = (
        "Date,Description,Amount,Running Bal.\n"
        "2026-10-02,Wire from Chase,2000.00,7000.00\n"
        "2026-10-03,Cloud Infrastructure Hosting,-500.00,6500.00\n"
    ).encode()

    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "30"},
        files=[
            ("files", ("chase_operating.csv", chase_csv, "text/csv")),
            ("files", ("svb_payroll.csv", svb_csv, "text/csv")),
        ],
    )
    assert response.status_code == 200
    body = response.json()

    assert body["accepted_count"] == 4
    # Multi-account total treasury: 13000 + 6500 = 19500
    assert body["current_balance"] == "19500.00"

    # Accounts breakdown
    assert len(body["accounts_breakdown"]) == 2
    assert body["accounts_breakdown"][0]["file_name"] == "chase_operating.csv"
    assert body["accounts_breakdown"][0]["closing_balance"] == "13000.00"
    assert body["accounts_breakdown"][1]["file_name"] == "svb_payroll.csv"
    assert body["accounts_breakdown"][1]["closing_balance"] == "6500.00"

    # Contra-transfer elimination
    assert body["internal_transfers_excluded"] == "2000.00"
    assert len(body["internal_transfers"]) == 1
    assert body["internal_transfers"][0]["amount"] == "2000.00"

    # Operational flows with contra-transfers excluded
    assert body["operational_inflows"] == "5000.00"
    assert body["operational_outflows"] == "500.00"


def test_analyze_api_with_multiple_csv_files_under_file_field():
    f1 = b"Date,Description,Amount,Running Bal.\n2026-10-01,Dep1,1000.00,5000.00\n"
    f2 = b"Date,Description,Amount,Running Bal.\n2026-10-02,Dep2,2000.00,7000.00\n"

    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "30"},
        files=[
            ("file", ("statement_a.csv", f1, "text/csv")),
            ("file", ("statement_b.csv", f2, "text/csv")),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted_count"] == 2
    assert body["accounts_breakdown"] is not None
    assert len(body["accounts_breakdown"]) == 2


def test_analyze_api_deduplicates_duplicate_uploaded_statement_files():
    f1 = b"Date,Description,Amount,Running Bal.\n2026-10-01,Dep1,1000.00,5000.00\n"
    f2 = b"Date,Description,Amount,Running Bal.\n2026-10-02,Dep2,2000.00,7000.00\n"

    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "30"},
        files=[
            ("files", ("statement_a.csv", f1, "text/csv")),
            ("files", ("statement_b.csv", f2, "text/csv")),
            ("files", ("statement_b.csv", f2, "text/csv")),
        ],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accounts_breakdown"] is not None
    assert len(body["accounts_breakdown"]) == 2


def test_analyze_adjust_inflow():
    payload = {
        "current_balance": "10000.00",
        "adjustment_type": "INFLOW",
        "amount": "2500.00",
        "daily_burn": "250.00",
        "currency": "USD",
        "effective_date": "2026-10-15",
    }
    response = client.post("/api/v1/analyze/adjust", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["current_balance"] == "12500.00"
    assert body["net_period_change"] == "2500.00"
    assert body["runway_days"] == 50
    assert body["projected_depletion_date"] == "2026-12-04"
    assert body["document_format"] == "MANUAL"


def test_analyze_adjust_outflow():
    payload = {
        "current_balance": "10000.00",
        "adjustment_type": "OUTFLOW",
        "amount": "4000.00",
        "daily_burn": "200.00",
        "currency": "USD",
        "effective_date": "2026-10-15",
    }
    response = client.post("/api/v1/analyze/adjust", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["current_balance"] == "6000.00"
    assert body["net_period_change"] == "-4000.00"
    assert body["runway_days"] == 30


def test_analyze_adjust_set_balance():
    payload = {
        "current_balance": "10000.00",
        "adjustment_type": "SET_BALANCE",
        "amount": "50000.00",
        "daily_burn": "500.00",
        "currency": "EUR",
        "effective_date": "2026-10-15",
    }
    response = client.post("/api/v1/analyze/adjust", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["current_balance"] == "50000.00"
    assert body["currency"] == "EUR"
    assert body["runway_days"] == 100


def test_analyze_summary_balance_only():
    payload = {
        "current_balance": "45000.00",
        "monthly_burn": "15000.00",
        "currency": "USD",
        "as_of_date": "2026-10-15",
    }
    response = client.post("/api/v1/analyze/summary", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["current_balance"] == "45000.00"
    assert body["average_daily_burn"] == "500.00"
    assert body["runway_days"] == 90
    assert body["cash_status"] == "WATCH"
    assert body["document_format"] == "MANUAL"








def test_quick_cash_rejects_bad_input_with_422():
    bad = [
        ("/api/v1/analyze/adjust", {"current_balance": "100.00", "adjustment_type": "INFLOW", "amount": "-5.00"}),
        ("/api/v1/analyze/adjust", {"current_balance": "100.00", "adjustment_type": "INFLOW", "amount": "5.00", "alert_threshold_days": 0}),
        ("/api/v1/analyze/adjust", {"current_balance": "100.00", "adjustment_type": "REFUND", "amount": "5.00"}),
        ("/api/v1/analyze/summary", {"current_balance": "100.00", "monthly_burn": "-1.00"}),
        ("/api/v1/analyze/summary", {"current_balance": "100.00", "currency": "dollars"}),
    ]
    for path, payload in bad:
        assert client.post(path, json=payload).status_code == 422, (path, payload)


def test_quick_cash_without_burn_leaves_runway_unknown():
    # No burn given means no runway: the API must not estimate one.
    body = client.post("/api/v1/analyze/summary", json={"current_balance": "42000.00"}).json()
    assert body["average_daily_burn"] == "0.00"
    assert body["runway_days"] is None
    assert body["projected_depletion_date"] is None


def test_multi_account_history_sums_to_the_current_balance():
    files = [
        ("files", (name, open(f"data/samples/{name}", "rb").read(), "text/csv"))
        for name in ("chase_operating_october.csv", "svb_payroll_october.csv")
    ]
    body = client.post("/api/v1/analyze", files=files).json()
    assert len(body["account_history"]) == 2
    assert body["balance_history"][-1]["balance"] == body["current_balance"]
    assert body["projection"][0] == {"date": body["end_date"], "balance": body["current_balance"]}


def test_scenario_levers_and_validation():
    base = {"current_balance": "1000.00", "average_daily_burn": "100.00", "anchor_date": "2026-10-01"}
    plain = client.post("/api/v1/analyze/scenario", json=base).json()
    collected = client.post(
        "/api/v1/analyze/scenario",
        json={**base, "one_off_inflows": [{"date": "2026-10-05", "amount": "500.00"}]},
    ).json()
    assert plain["forecast"]["days_until_deficit"] == 11
    assert collected["forecast"]["days_until_deficit"] == 16
    assert len(plain["projection"]) == 91
    for bad in ({**base, "variable_cut_pct": "120"}, {**base, "average_daily_burn": "-1"}, {**base, "days": 0}):
        assert client.post("/api/v1/analyze/scenario", json=bad).status_code == 422


def test_adjustment_lands_on_one_account_and_total_is_their_sum():
    payload = {
        "current_balance": "1500.00",
        "adjustment_type": "OUTFLOW",
        "amount": "200.50",
        "account_id": "Chase",
        "accounts": [{"account_id": "Chase", "balance": "1000.00"}, {"account_id": "SVB", "balance": "500.00"}],
        "effective_date": "2026-10-20",
    }
    body = client.post("/api/v1/analyze/adjust", json=payload).json()
    assert body["current_balance"] == "1299.50"
    assert body["net_period_change"] == "-200.50"
    assert {a["account_id"]: a["closing_balance"] for a in body["accounts_breakdown"]} == {"Chase": "799.50", "SVB": "500.00"}

    # A new account id opens that account with the amount set.
    opened = client.post(
        "/api/v1/analyze/adjust",
        json={**payload, "adjustment_type": "SET_BALANCE", "amount": "250.00", "account_id": "Petty cash"},
    ).json()
    assert opened["current_balance"] == "1750.00"
    assert len(opened["accounts_breakdown"]) == 3


def test_adjustment_rejects_duplicate_or_unnamed_accounts():
    base = {"current_balance": "0", "adjustment_type": "INFLOW", "amount": "1.00"}
    dup = {**base, "account_id": "A", "accounts": [{"account_id": "A", "balance": "1"}, {"account_id": "A", "balance": "2"}]}
    unnamed = {**base, "accounts": [{"account_id": "A", "balance": "1"}]}
    assert client.post("/api/v1/analyze/adjust", json=dup).status_code == 422
    assert client.post("/api/v1/analyze/adjust", json=unnamed).status_code == 422
