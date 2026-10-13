---
name: pytest-financial-testing
description: "Authoring automated PyTest test suites and deterministic verification for fintech calculations. Use when testing cash runway formulas, DSCR calculations, loan factor rate to APR conversions, and mocking bank transaction fixtures."
---

# PyTest Financial Testing Framework

Deterministic quality assurance patterns for the SME Finance Copilot.

## 1. Testing Financial Formulas

Always use `Decimal` with fixed quantization in test assertions:
```python
from decimal import Decimal
import pytest
from services.cashflow import calculate_runway, calculate_true_apr

def test_runway_calculation_exact():
    cash_balance = Decimal("45000.00")
    monthly_burn = Decimal("15000.00")
    # Runway in months
    runway = calculate_runway(cash_balance, monthly_burn)
    assert runway == Decimal("3.00")

def test_negative_burn_rate_zero_division():
    cash_balance = Decimal("50000.00")
    monthly_burn = Decimal("-2000.00") # Net cash-flow positive
    runway = calculate_runway(cash_balance, monthly_burn)
    assert runway == Decimal("Infinity")

def test_factor_rate_to_apr_conversion():
    advance_amount = Decimal("10000.00")
    total_repayment = Decimal("12500.00") # 1.25x factor rate
    term_months = 6
    true_apr = calculate_true_apr(advance_amount, total_repayment, term_months)
    # 25% fee over 6 months annualized is ~50% APR
    assert true_apr > Decimal("45.00")
```

## 2. Edge Case Test Matrix

- **Zero Balance / Negative Balance**: Bank overdraft conditions.
- **DSO Extension**: Customers paying in 75 days instead of 30 days.
- **Payday Cash Dip**: Sudden \$20k payroll debit against \$15k balance.
- **Double Invoicing**: Submitting identical invoice hashes triggers blockchain rejection.
