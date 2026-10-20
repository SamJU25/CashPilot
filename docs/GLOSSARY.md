# SME Finance Copilot — Ubiquitous Domain Glossary

This glossary defines standard financial and technical terms used throughout the SME Finance Copilot codebase, data models, calculations, and agent prompts. Every developer and agent must use these exact terms to prevent semantic drift.

---

## 1. Core SME Working Capital & Liquidity Metrics

### Cash Conversion Cycle (CCC)
* **Definition**: The time (in days) it takes for a business to convert investments in inventory and resources into cash flows from sales.
* **Formula**: `CCC = DIO + DSO - DPO`
* **Significance**: Explains why profitable businesses experience insolvency. A business with a long CCC must finance its operating cycle with working capital debt or cash reserves.

### Days Sales Outstanding (DSO)
* **Definition**: The average number of days it takes for a company to collect payment after a sale has been made.
* **Formula**: `(Accounts Receivable / Total Credit Sales) * Number of Days`
* **Target**: Lower is better. Rising DSO signals delayed client payments and incoming cash crunches.

### Days Inventory Outstanding (DIO)
* **Definition**: The average number of days inventory sits before being sold.
* **Formula**: `(Average Inventory / Cost of Goods Sold) * 365`

### Days Payables Outstanding (DPO)
* **Definition**: The average number of days a company takes to pay its suppliers and vendors.
* **Formula**: `(Accounts Payable / Cost of Goods Sold) * 365`

### Cash Runway
* **Definition**: The number of months a business can survive before running out of cash at its current net burn rate.
* **Formula**: `Current Cash Balance / Net Monthly Burn Rate`
* **Alert Thresholds**:
  - `> 3 months`: Healthy (Green)
  - `1 - 3 months`: Warning (Yellow)
  - `< 1 month`: Critical (Red)

### Net Monthly Burn Rate
* **Definition**: Net cash lost per month from operations.
* **Formula**: `Total Monthly Cash Inflows - Total Monthly Cash Outflows` (when outflows > inflows).

### Debt Service Coverage Ratio (DSCR)
* **Definition**: Measurement of available cash flow to pay current debt obligations (principal + interest).
* **Formula**: `Net Operating Income / Total Debt Service`
* **Benchmark**: Standard lenders require `DSCR >= 1.25x`. Below `1.0x` indicates the business cannot service its debt from operating income alone.

### Daily Average Balance (DAB)
* **Definition**: The arithmetic mean of end-of-day bank ledger balances across a 30, 60, or 90-day assessment window.
* **Significance**: Core alternative underwriting metric used by digital lenders (e.g. WeBank) to verify operational liquidity when audited statements are absent.

### Non-Sufficient Funds (NSF) Frequency
* **Definition**: Number of times an account had insufficient funds to honor a check, debit, or ACH withdrawal.
* **Significance**: Primary red flag in digital underwriting. More than 2-3 NSF occurrences in a 90-day window typically triggers automated loan rejection.

---

## 2. Financing Instruments & Truth-in-Lending

### Annual Percentage Rate (APR)
* **Definition**: The annualized cost of credit expressed as a percentage, including interest, fees, and compounding periods.
* **Truth-in-Lending Invariant**: All financing offers must be converted to true APR to prevent predatory loan masking.

### Factor Rate
* **Definition**: A fixed multiplier used in Merchant Cash Advances (MCA) and short-term debt (e.g., 1.25x factor on $10,000 means repaying $12,500).
* **Pitfall**: A 1.25x factor paid over 4 months represents an effective APR exceeding 70-100%, not a simple 25% cost.

### Invoice Factoring / Invoice Discounting
* **Definition**: Selling outstanding customer invoices (Accounts Receivable) to a lender at a discount (typically 80-90% upfront advance) to unlock immediate liquidity.

### Purchase Order (PO) Financing
* **Definition**: Short-term funding where the lender pays suppliers directly to produce goods for a confirmed, non-cancellable customer purchase order.

### Revenue-Based Financing (RBF)
* **Definition**: An advance repaid as a fixed percentage of daily or weekly gross revenues, accommodating cyclical or seasonal sales variations.

---

## 3. Digital Underwriting Architecture (WeBank Model)

### Digital SME Lending Model ("Weiyidai")
* **Concept**: Zero-collateral, pure digital credit scoring pioneered by WeBank.
* **Core Data Pillars**:
  1. Transactional bank streams (DAB, deposit consistency, inflow velocity).
  2. B2B VAT e-invoices and tax reporting data to verify actual commercial activity.
  3. Real-time anti-fraud network graph analysis.

### Consortium Blockchain (FISCO BCOS) Audit Trail
* **Concept**: An enterprise permissioned blockchain utilized to register cryptographic hashes (`SHA-256`) of B2B invoices.
* **Purpose**: Prevents "double-financing" (pledging the same invoice to multiple lenders simultaneously) and provides tamper-proof audit trails for supply chain finance.

---

## 4. Agentic System Governance & Security

### 3-Tier Security Matrix
* **Tier 1 (Observation)**: Read-only data ingestion and analysis. No human confirmation needed.
* **Tier 2 (Staging)**: Generating actionable proposals or structuring applications. Staged in an immutable ledger queue.
* **Tier 3 (Execution)**: Irreversible financial movement or binding contractual commitments. Mandatory Human-in-the-Loop (HITL) 2FA verification.
