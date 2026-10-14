"""
System health and operational invariant status endpoint.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["Health"])


class HealthStatus(BaseModel):
    status: str
    version: str
    form_factor: str
    active_invariants: list[str]


@router.get("/health", response_model=HealthStatus)
async def get_health_status():
    return HealthStatus(
        status="healthy",
        version="1.0.0",
        form_factor="Responsive Web Application + PWA",
        active_invariants=[
            "Deterministic Decimal Arithmetic (0% LLM math)",
            "Three-Tier Security Gate (Tier 3 WebAuthn required)",
            "PostgreSQL Row-Level Security (Multi-tenant isolation)",
            "Rust-compiled Pydantic v2 Type Validation",
            "Consortium Blockchain Anchor (FISCO BCOS)"
        ]
    )
