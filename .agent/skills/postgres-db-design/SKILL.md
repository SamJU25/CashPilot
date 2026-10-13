---
name: postgres-db-design
description: "PostgreSQL relational schema design and optimization for SME finance ledgers. Use when architecting tables for bank transactions, invoices, credit underwriting dossiers, immutable audit logs, and configuring indexes for time-series queries."
---

# PostgreSQL Database Design for SME Finance

ACID-compliant relational design for financial transactions, double-entry ledgers, and tamper-proof audit trails.

## 1. Core Financial Schema

```sql
-- Organizations & Small Business Entities
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_name VARCHAR(255) NOT NULL,
    tax_id VARCHAR(50) UNIQUE NOT NULL,
    industry_code VARCHAR(10) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Bank Accounts & Sync Status
CREATE TABLE bank_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    account_number_masked VARCHAR(20) NOT NULL,
    institution_name VARCHAR(100) NOT NULL,
    current_balance NUMERIC(15, 2) NOT NULL,
    available_balance NUMERIC(15, 2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Time-Series Financial Transactions
CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES bank_accounts(id) ON DELETE CASCADE,
    transaction_date DATE NOT NULL,
    amount NUMERIC(15, 2) NOT NULL, -- Negative for outflows, positive for inflows
    category VARCHAR(50) NOT NULL,  -- Payroll, Inventory, Client Deposit, Rent, Tax
    description TEXT NOT NULL,
    is_reconciled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_transactions_acc_date ON transactions(account_id, transaction_date DESC);

-- B2B Invoices for Factoring & On-Chain Anchoring
CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    invoice_number VARCHAR(100) NOT NULL,
    debtor_name VARCHAR(255) NOT NULL,
    invoice_amount NUMERIC(15, 2) NOT NULL,
    issue_date DATE NOT NULL,
    due_date DATE NOT NULL,
    status VARCHAR(30) DEFAULT 'unpaid', -- unpaid, factoring_staged, paid, overdue
    invoice_hash VARCHAR(64) NOT NULL,   -- SHA-256 for FISCO BCOS blockchain anchor
    on_chain_tx_id VARCHAR(128),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Immutable Security & Permission Audit Log
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    org_id UUID NOT NULL,
    actor_type VARCHAR(20) NOT NULL,   -- 'AI_AGENT' or 'USER'
    tier_level INT NOT NULL,           -- 1, 2, or 3
    action_name VARCHAR(100) NOT NULL, -- e.g., 'STAGED_FACTORING_PROPOSAL', '2FA_EXECUTED_DISBURSEMENT'
    payload JSONB NOT NULL,
    ip_address VARCHAR(45),
    timestamp TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_logs_org ON audit_logs(org_id, timestamp DESC);
```
