"""
Three-Tier Security Gate and Action Intent Staging.
Aligns with docs/security.md Section 1 and docs/system.md Section 4.2.
"""

from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class SecurityTier(str, Enum):
    TIER_1_OBSERVATION = "TIER_1_OBSERVATION"  # Autonomous read-only queries
    TIER_2_STAGING = "TIER_2_STAGING"          # Proposal preparation, no money moves
    TIER_3_EXECUTION = "TIER_3_EXECUTION"      # Moves money or commits the business: never done by CashPilot


class StagedActionIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    
    id: str
    tenant_id: str
    action_type: str = Field(description="FACTOR_INVOICE, DRAW_CREDIT_LINE, or TRANSFER")
    amount_cents: int = Field(gt=0, description="Exact integer amount in cents")
    target_identifier: str
    status: str = Field(default="STAGED_PENDING_HITL")
    staged_at: datetime


def requires_owner_action(action_type: str) -> bool:
    """
    True for Tier 3 actions (credit draws, transfers, invoice sales). CashPilot has no bank or lender
    connection, so these end as a request the owner sends; nothing in the system can carry them out.
    Evaluated by reference via DecisionEngineRegistry (zero hardcoded rules).
    """
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    req = DecisionRequest(
        domain=DecisionDomain.SECURITY_GATE,
        input_state={"action_type": action_type},
        execution_mode="DETERMINISTIC_ONLY",
    )
    res = DecisionEngineRegistry.get_instance().evaluate(req)
    return bool(res.output_payload.get("requires_owner_action", res.selected_choice == "TIER_3_EXECUTION"))
