# Runtime Subagent Topology & Communication Contract

- **Status**: Definitive Runtime Architecture
- **Date**: 2026-10-14
- **Scope**: Production multi-agent routing, tool permissions, and deterministic boundaries.

---

## 1. Runtime Topology Matrix

At runtime, the Copilot executes **1 Lead Orchestrator + 4 Specialized Functional Squads + 1 Security Gatekeeper**:

```
                              [ Human SME Business Owner ]
                                           │
                                           ▼ (WebAuthn / Chat / Generative UI)
                           ┌───────────────────────────────┐
                           │       LEAD ORCHESTRATOR       │
                           │ • User Dialogue & Intent Route│
                           │ • Zero Database Write Rights  │
                           └───────────────┬───────────────┘
                                           │
         ┌──────────────────┬──────────────┴─────┬──────────────────┐
         ▼                  ▼                    ▼                  ▼
  ┌──────────────┐   ┌──────────────┐     ┌──────────────┐   ┌──────────────┐
  │   SQUAD 1    │   │   SQUAD 2    │     │   SQUAD 3    │   │   SQUAD 4    │
  │  Ingestion   │   │  Diagnostic  │     │Risk Forecast │   │ Underwriting │
  │  & Privacy   │   │  CFO Engine  │     │ & Alerting   │   │  & Matching  │
  ├──────────────┤   ├──────────────┤     ├──────────────┤   ├──────────────┤
  │ Presidio PII │   │ Pure Python  │     │ MAPIE bounds │   │ PuLP MILP    │
  │ Pydantic v2  │   │ Decimal math │     │ P10/P50/P90  │   │ True APR >36%│
  └──────────────┘   └──────────────┘     └──────────────┘   └──────────────┘
         │                  │                    │                  │
         └──────────────────┴──────────────┬─────┴──────────────────┘
                                           │ Proposes ActionIntent
                                           ▼
                           ┌───────────────────────────────┐
                           │    THREE-TIER GATEKEEPER      │
                           │ • Tier 1: Read-Only Ledger    │
                           │ • Tier 2: Staged Queue        │
                           │ • Tier 3: WebAuthn 2FA + BCOS │
                           └───────────────────────────────┘
```

---

## 2. Squad Role, Tools, and Security Invariant Specifications

### 1. Lead Orchestrator (Supervisor)
- **Role**: Natural language interface, context coordinator, and explanation synthesizer.
- **Tools**: `route_to_squad()`, `render_generative_ui()`, `explain_diagnostics()`.
- **Security Boundary**: Strictly read-only. Has zero database write privileges and zero payment gateway credentials.

### 2. Squad 1: Ingestion & Privacy Squad
- **Role**: Bank CSV parsing, PDF invoice extraction, and zero-leakage PII sanitization.
- **Tools**: `presidio_scrub()`, `parse_bank_csv()`, `validate_invoice_schema()`.
- **Security Boundary**: Tier 1 (Observation). Masks names, phone numbers, and SSNs before any data reaches an LLM reasoning context.

### 3. Squad 2: Diagnostic CFO Engine
- **Role**: High-precision financial health scoring, Daily Average Balance (DAB), Cash Runway, Net Burn, and DSCR.
- **Tools**: `calc_runway()`, `calc_dscr()`, `calc_dab()`, `calc_ccc()`.
- **Security Boundary**: **0% LLM Math**. All formulas execute in Python `decimal.Decimal`. Output is passed as structured JSON directly to the frontend.

### 4. Squad 3: Risk Forecasting & Alerting Squad
- **Role**: Predictive cash crunch alerting across 30/60/90-day horizons.
- **Tools**: `forecast_cash_conformal()`, `compute_dso_hazard_curve()`, `emit_cash_alert()`.
- **Security Boundary**: Generates mathematical confidence intervals (P10/P50/P90) using MAPIE. Alerts are severity-coded (`LOW`, `MEDIUM`, `CRITICAL`).

### 5. Squad 4: Underwriting & Matching Squad
- **Role**: Matches cash deficits with optimal financing (credit line, factoring, PO loan) using mathematical optimization.
- **Tools**: `optimize_financing_pulp()`, `convert_factor_rate_to_apr()`, `check_predatory_apr()`.
- **Security Boundary**: Truth-in-lending compliance. Any facility exceeding 36% APR is flagged as high-risk/predatory.

### 6. The Three-Tier Security Gatekeeper (The Enforcer)
- **Role**: Permission enforcement, immutable staging ledger, and consortium blockchain registration.
- **Tools**: `stage_action_intent()`, `verify_webauthn_biometric()`, `fisco_bcos_register_invoice()`.
- **Security Boundary**: Tier 3 financial execution halts the system and requires physical user biometric confirmation (TouchID/Windows Hello).
