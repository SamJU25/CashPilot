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
        form_factor="Local-first FastAPI service with Next.js client",
        active_invariants=[
            "All financial calculations use Python Decimal arithmetic",
            "Statement uploads are size- and page-validated before analysis",
            "Action staging requires a signed tenant token; drafted actions are never executed, the owner sends them",
        ]
    )
