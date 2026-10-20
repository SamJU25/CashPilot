"""Balance history for the chart, and the what-if levers on the shared cash simulation."""

from datetime import date
from decimal import Decimal

from services.calculations.balance_history import daily_balance_history
from services.calculations.predictive_cash import (
    CashScenario,
    DetectedObligation,
    calculate_predictive_cash,
    simulate_balances,
)
from services.ingestion.csv_parser import DemoTransaction

D = Decimal


def tx(n, day, amount, closing, desc="Card"):
    return DemoTransaction(n, f"t{n}", date(2026, 10, day), D(amount), "USD", desc, D(closing))


def test_history_carries_balances_over_quiet_days():
    rows = [tx(1, 1, "-10", "90"), tx(2, 4, "5", "95")]
    total, per = daily_balance_history(rows, lambda r: "A")
    assert [b for _, b in total] == [D("90"), D("90"), D("90"), D("95")]
    assert [b for _, b in per["A"]] == [D("90"), D("90"), D("90"), D("95")]


def test_history_total_uses_opening_before_and_last_after_each_account():
    a = [tx(1, 1, "-10", "90"), tx(2, 2, "-10", "80")]
    b = [tx(3, 2, "50", "550"), tx(4, 3, "-50", "500")]
    owner = {id(r): "A" for r in a} | {id(r): "B" for r in b}
    total, per = daily_balance_history(a + b, lambda r: owner[id(r)])
    # Oct 1: A 90, B not started yet so its opening 500 counts; Oct 3: A ended at 80, B 500.
    assert total == [(date(2026, 10, 1), D("590")), (date(2026, 10, 2), D("630")), (date(2026, 10, 3), D("580"))]
    assert per["A"][-1] == (date(2026, 10, 3), None)
    assert per["B"][0] == (date(2026, 10, 1), None)


PAYROLL = DetectedObligation("PAYROLL", D("3000.00"), 15)


def test_payroll_leaves_on_its_day_and_extra_payroll_rides_with_it():
    sim = simulate_balances(D("10000"), D("200"), [PAYROLL], date(2026, 10, 1), 20, CashScenario(extra_monthly_payroll=D("500")))
    by_day = {d.day: b for d, b, _ in sim}
    # Variable burn is (200*30 - 3000)/30 = 100 a day; payroll day also pays 3000 + 500.
    assert by_day[14] == D("10000") - 13 * D("100")
    assert by_day[15] == by_day[14] - D("100") - D("3500")


def test_cut_applies_to_day_to_day_spending_only():
    base = simulate_balances(D("10000"), D("200"), [PAYROLL], date(2026, 10, 1), 30)
    cut = simulate_balances(D("10000"), D("200"), [PAYROLL], date(2026, 10, 1), 30, CashScenario(variable_cut_pct=D("50")))
    assert base[0][1] == D("9900") and cut[0][1] == D("9950")


def test_extra_payroll_without_a_payroll_day_is_spread_not_dated():
    sim = simulate_balances(D("1000"), D("10"), [], date(2026, 10, 1), 2, CashScenario(extra_monthly_payroll=D("300")))
    assert [b for _, b, _ in sim] == [D("980"), D("960")]


def test_collected_invoice_moves_the_shortfall_later():
    args = (D("1000"), D("100"), [])
    base = calculate_predictive_cash(*args, anchor_date=date(2026, 10, 1), obligations=[])
    later = calculate_predictive_cash(
        *args, anchor_date=date(2026, 10, 1), obligations=[],
        scenario=CashScenario(one_off_inflows=((date(2026, 10, 5), D("500")),)),
    )
    assert base.days_until_deficit == 11
    assert later.days_until_deficit == 16


def test_extra_payroll_uses_the_known_payday_even_when_income_covers_spending():
    # Net burn 0: obligations are not deducted separately, but a new hire is still paid on payday.
    sim = simulate_balances(D("10000"), D("0"), [PAYROLL], date(2026, 10, 1), 20, CashScenario(extra_monthly_payroll=D("1000")))
    by_day = {d.day: b for d, b, _ in sim}
    assert by_day[14] == D("10000") and by_day[15] == D("9000")
