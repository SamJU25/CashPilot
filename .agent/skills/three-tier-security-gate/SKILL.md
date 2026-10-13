---
name: three-tier-security-gate
description: "Enforces the Three-Tier Permission Matrix for autonomous financial AI participants. Use when implementing permission gates, staging financial intents, verifying Human-in-the-Loop (HITL) 2FA authorization, and masking PII before LLM reasoning."
---

# Three-Tier Security Gate Protocol

Core security invariant governing all autonomous actions in the SME Finance Copilot.

## 1. The Permission Matrix

| Tier | Category | Allowed Actions | Execution Authority |
|---|---|---|---|
| **Tier 1** | Observation & Telemetry | CSV ingestion, invoice OCR, ratio calculation, 30-day runway projection, cash flow simulations | Autonomous Background Execution |
| **Tier 2** | Staging Intent Proposals | Drafting loan applications, structuring invoice factoring dossiers, composing vendor payment reminders | Staged in Immutable Intent Queue (Zero Money Movement) |
| **Tier 3** | Irreversible Execution | Drawing on credit lines, executing wires, factoring invoices, signing lending contracts | **HALT**: Requires Explicit Human-in-the-Loop 2FA Biometric/OTP |

## 2. Implementation Gatekeeper

```python
async def execute_copilot_action(action: CopilotAction, user: User, db: AsyncSession):
    if action.tier == PermissionTier.TIER_1:
        return await action.execute_read_only(db)
        
    elif action.tier == PermissionTier.TIER_2:
        # Push to immutable intent queue for user review
        staged_intent = await queue_staged_intent(action, user, db)
        await log_audit_event(user.id, tier=2, action="STAGED_PROPOSAL", payload=action.dict())
        return {"status": "STAGED", "intent_id": staged_intent.id, "message": "Proposal staged for review"}
        
    elif action.tier == PermissionTier.TIER_3:
        # Verify 2FA token
        if not await verify_user_2fa_otp(user.id, action.two_factor_code):
            raise SecurityGateError("Tier 3 action rejected: Invalid or missing 2FA authorization.")
            
        result = await action.execute_financial_mutation(db)
        await log_audit_event(user.id, tier=3, action="EXECUTED_MUTATION", payload=action.dict())
        return {"status": "EXECUTED", "result": result}
```

## 3. PII Sanitization

Before passing raw bank CSVs or invoice text to any LLM prompt:
- Mask Bank Account Numbers: `****-****-****-1234`
- Mask Social Security / Tax IDs: `***-**-6789`
- Mask Personal Phone Numbers & Physical Residential Addresses.
