---
name: three-tier-security-gate
description: "Enforces the Three-Tier Permission Matrix for autonomous financial AI participants. Use when implementing permission gates, staging financial intents, keeping Tier 3 actions owner-sent (never executed), and masking PII before LLM reasoning."
---

# Three-Tier Security Gate Protocol

Core security invariant governing all autonomous actions in the SME Finance Copilot.

## 1. The Permission Matrix

| Tier | Category | Allowed Actions | Execution Authority |
|---|---|---|---|
| **Tier 1** | Observation & Telemetry | CSV ingestion, invoice OCR, ratio calculation, 30-day runway projection, cash flow simulations | Autonomous Background Execution |
| **Tier 2** | Staging Intent Proposals | Drafting loan applications, structuring invoice factoring dossiers, composing vendor payment reminders | Staged in Immutable Intent Queue (Zero Money Movement) |
| **Tier 3** | Owner-Sent Actions | Drawing on credit lines, executing wires, factoring invoices, signing lending contracts | **Never executed**: drafted as a request the owner prepares and sends themselves |

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
        # No execution path exists: the system holds no payment credentials. The owner gets a
        # drafted request to prepare and send themselves (POST /api/v1/actions/{id}/prepare).
        staged_intent = await queue_staged_intent(action, user, db)
        await log_audit_event(user.id, tier=3, action="DRAFTED_FOR_OWNER", payload=action.dict())
        return {"status": "STAGED", "intent_id": staged_intent.id, "message": "Request drafted; the owner sends it"}
```

## 3. PII Sanitization

Before passing raw bank CSVs or invoice text to any LLM prompt:
- Mask Bank Account Numbers: `****-****-****-1234`
- Mask Social Security / Tax IDs: `***-**-6789`
- Mask Personal Phone Numbers & Physical Residential Addresses.
