---
name: stripe-payments-integration
description: "Best practices for integrating Stripe and Open Banking payment rails in the SME Finance Copilot. Use when configuring payment intents, invoice webhooks, fee reconciliation, idempotency keys, and payout disbursements."
---

# Stripe & Open Banking Payments Integration

Rules and patterns for safe, reliable payment gateway integration and transaction handling.

## 1. Idempotency & Concurrency

- **Mandatory Idempotency Keys**: Every mutating call (creating PaymentIntents, issuing payout disbursements) must send an `Idempotency-Key` header derived deterministically (e.g., `f"payout_{application_id}_{user_id}"`).
- **Race Condition Prevention**: Handle duplicate incoming webhook deliveries gracefully by recording processed event IDs in an immutable `processed_events` table within an ACID transaction.

## 2. Webhook Signature Verification

Always verify signatures using the official SDK:
```python
import stripe
from fastapi import Request, HTTPException

async def verify_stripe_webhook(request: Request, webhook_secret: str) -> stripe.Event:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        return event
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
```

## 3. Reconciliation & Fee Accounting

- Break down every transaction into `gross_amount`, `fee_amount`, and `net_amount`.
- Never record gross payout as pure revenue; automatically map gateway processing fees to an Operating Expense ledger code.
