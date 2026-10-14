# SME Finance Copilot: Complete System Design Specification

- **Document Type**: Technical System Design (Concrete Implementation Mechanics)
- **Status**: Definitive Specification
- **Date**: 2026-10-14
- **Target**: FinTechathon 2026 Track E (Tsinghua University PBCSF & WeBank)

---

## 1. Features Adopted from Research & Mathematical Formulation

The system integrates seven specific algorithms and protocols evaluated during research:

### 1.1 Deterministic CFO Financial Metrics (Squad 2)
- **Daily Average Balance (DAB)**:
  $$\text{DAB} = \frac{1}{N} \sum_{i=1}^N \text{closing\_balance}_i$$
  Calculated using Python `decimal.Decimal` over 30, 60, and 90-day rolling windows. Replaces unaudited balance sheets with transactional truth.
- **Cash Runway & Net Burn Rate**:
  $$\text{Daily Burn} = \frac{\sum \text{Operating Expenses} - \sum \text{Operating Inflows}}{\text{Days}}$$
  $$\text{Runway (Days)} = \begin{cases} 999 & \text{if Daily Burn} \le 0 \\ \lfloor \frac{\text{Cash Balance}}{\text{Daily Burn}} \rfloor & \text{if Daily Burn} > 0 \end{cases}$$
- **Debt Service Coverage Ratio (DSCR)**:
  $$\text{DSCR} = \frac{\text{Net Operating Income}}{\text{Total Debt Service}}$$
  Benchmark: $\text{DSCR} \ge 1.25$ indicates qualifying liquidity for bank credit lines.

### 1.2 Conformal Cash Forecasting & Survival Curves (Squad 3)
- **MAPIE Conformal Risk Intervals**:
  Instead of an uncalibrated point estimate $\hat{y}$, MAPIE generates a calibrated interval $[y_{\text{low}}, y_{\text{high}}]$ at $(1 - \alpha) = 90\%$ confidence:
  $$P\left(y_{t+k} \in [P_{10}, P_{90}]\right) \ge 0.90$$
  $P_{10}$ represents the stress-tested worst-case cash balance used to trigger early-warning crunch alerts.
- **DSO Customer Payment Hazard Modeling (Lifelines)**:
  Applies the Kaplan-Meier survival estimator to invoice age:
  $$\hat{S}(t) = \prod_{t_i \le t} \left(1 - \frac{d_i}{n_i}\right)$$
  Computes the exact probability of an invoice being paid within 30, 60, or 90 days based on buyer historical settlement latency.

### 1.3 Mixed-Integer Linear Programming Liquidity Matcher (Squad 4)
- **PuLP Optimization Formulation**:
  Solves the cost-minimizing liquidity allocation across $M$ credit facilities:
  $$\min \sum_{j=1}^M \left( \text{APR}_j \cdot x_j + \text{OriginationFee}_j \cdot y_j \right)$$
  Subject to:
  $$\sum_{j=1}^M x_j \ge \text{Projected Deficit}, \quad 0 \le x_j \le \text{MaxLimit}_j \cdot y_j, \quad y_j \in \{0, 1\}$$
- **Truth-in-Lending APR Conversion**:
  Converts deceptive merchant factor rates into true APR:
  $$\text{APR} = \left( \frac{\text{Factor Rate} - 1.0}{\text{Duration in Days}} \right) \times 365 \times 100$$
  Rule: Any loan exceeding $36.0\%$ APR is tagged with `flag = PREDATORY_HIGH_RISK` and excluded from automatic recommendations.

---

## 2. Frontend Backbone Specification

### 2.1 Technology Stack & Rendering Strategy
- **Framework**: Next.js 14 App Router with React Server Components (RSC).
- **Styling**: Tailwind CSS with strict monospace numerical typography:
  ```css
  .tabular-numbers {
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }
  ```
- **Motion Physics**: Emil Kowalski spring transitions:
  - Duration: $\le 280\text{ms}$
  - Spring tension: $170$, friction: $26$ (zero bouncy cartoon overshoot).

### 2.2 Four-State Component Protocol
Every financial card, alert item, and ledger table must implement all four states:
1. **Loading State**: Monochromatic pulse skeleton matching the exact dimension of the loaded data.
2. **Empty State**: Plain-English action prompt (e.g., "No bank transactions detected. Upload your first CSV to generate runway diagnostics.").
3. **Error State**: Non-blocking banner with deterministic error reason and a retry action button.
4. **Populated State**: Monospace numerical display with directional variance indicators ($\pm \Delta\%$).

### 2.3 Real-Time Streaming Architecture
- **WebSocket Protocol**: `/ws/v1/live-alerts`
- **Payload Schema**:
  ```typescript
  interface LiveAlertPayload {
    alert_id: string;
    timestamp: string;
    severity: 'LOW' | 'MEDIUM' | 'CRITICAL';
    title: string;
    projected_deficit_cents: number;
    projected_date: string;
    suggested_intent_id?: string;
  }
  ```

---

## 3. Backend Backbone Specification

### 3.1 Technology Stack & Application Server
- **Runtime**: Python 3.12+ with FastAPI (Asynchronous ASGI).
- **Driver**: `asyncpg` utilizing PostgreSQL binary wire protocol (prepared statements).
- **Validation**: Pydantic v2 (Rust-compiled) with `ConfigDict(extra="forbid", strict=True)`.

### 3.2 Data Models & Schema Contracts

```python
# Core Domain Schemas (Pydantic v2)
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional, Literal
from datetime import date, datetime

class BankTransaction(BaseModel):
    id: str
    tenant_id: str
    post_date: date
    amount: Decimal = Field(decimal_places=2)
    counterparty: str = Field(min_length=1, max_length=120)
    category: str
    is_nsf: bool = False

class ActionIntent(BaseModel):
    id: str
    tenant_id: str
    action_type: Literal["FACTOR_INVOICE", "DRAW_CREDIT_LINE", "TRANSFER"]
    amount_cents: int = Field(gt=0)
    target_identifier: str
    status: Literal["STAGED_PENDING_HITL", "EXECUTED", "REJECTED"]
    staged_at: datetime
    biometric_signature: Optional[str] = None
```

### 3.3 Database Table Architecture (PostgreSQL 16)
1. `tenants`: Master company registry with encryption key references.
2. `transactions`: Ingested bank ledger entries with index on `(tenant_id, post_date)`.
3. `invoices`: B2B customer invoices with SHA-256 hash and FISCO BCOS status.
4. `action_intents`: The immutable staging queue for Tier 2/3 proposals.
5. `ledger_entries`: Append-only double-entry financial log (`UPDATE` and `DELETE` revoked).

---

## 4. LLM Brain & Gateway Specification

### 4.1 Client Gateway Pipeline (`LiteLLM` + `Instructor`)
```
[ Incoming Query ] ──> [ Deterministic Pre-Calculator (Python) ]
                                   │
                                   ▼
                      [ System Prompt Assembler ]
                      (Injects verified numbers + XML boundary)
                                   │
                                   ▼
                        [ LiteLLM Model Router ]
                      (Gemini / GPT-4o / DeepSeek / Ollama)
                                   │
                                   ▼
                       [ Instructor Parser (JSON) ]
                      (Enforces CopilotResponse Schema)
```

### 4.2 Configuration Matrix (`.env`)
- `LLM_MODEL`: `gemini/gemini-2.0-flash` (Cloud) or `ollama/llama3.1:8b` (Local Air-Gapped).
- `LLM_TEMPERATURE`: `0.1` (Minimizes creative variance).
- `LLM_MAX_TOKENS`: `1024`.

---

## 5. Consortium Blockchain Engine (FISCO BCOS)

### 5.1 Smart Contract Specification (`InvoiceRegistry.sol`)
```solidity
// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.20;

contract InvoiceRegistry {
    enum Status { UNREGISTERED, PLEDGED, SETTLED }

    struct InvoiceRecord {
        bytes32 invoiceHash;
        uint256 lenderId;
        uint256 pledgedTimestamp;
        Status status;
    }

    mapping(bytes32 => InvoiceRecord) public registry;

    event InvoicePledged(bytes32 indexed hash, uint256 indexed lenderId, uint256 timestamp);

    function pledgeInvoice(bytes32 hash, uint256 lenderId) external {
        InvoiceRecord storage record = registry[hash];
        require(record.status == Status.UNREGISTERED, "ERR_INVOICE_ALREADY_PLEDGED");
        
        record.invoiceHash = hash;
        record.lenderId = lenderId;
        record.pledgedTimestamp = block.timestamp;
        record.status = Status.PLEDGED;

        emit InvoicePledged(hash, lenderId, block.timestamp);
    }
}
```

### 5.2 Canonical Hashing Algorithm
Before registration, invoice fields are normalized and hashed:
$$\text{hash} = \text{keccak256}\left(\text{encodePacked}(\text{tax\_id}, \text{buyer\_id}, \text{invoice\_num}, \text{amount\_cents})\right)$$
Guarantees identical cryptographic hashes across independent bank nodes.
