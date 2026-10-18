"""
FastAPI Main Application Entrypoint.
Configures CORS, Security Headers, and Router Mounts.
Aligns with docs/system.md Section 4 and docs/security.md Section 4.
"""

import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes.health import router as health_router
from api.routes.analyze import router as analyze_router
from api.routes.actions import router as actions_router
from api.routes.underwrite import router as underwrite_router
from api.routes.agent import router as agent_router
from api.routes.decision import router as decision_router
from api.routes.auth import router as auth_router

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Pre-warm decision registry, knowledge cards, and FastEmbed ONNX semantic router
    # in a background daemon thread so first user chat turn responds in <50ms.
    from services.decision.registry import DecisionEngineRegistry
    from services.agent.knowledge import retrieve_cards
    from services.agent.dynamic_router import FastEmbedSemanticRouter
    from services.security.crypto import validate_configuration

    validate_configuration()
    DecisionEngineRegistry.get_instance()

    def _warmup_background():
        try:
            retrieve_cards("cash runway")
        except Exception:
            pass
        try:
            FastEmbedSemanticRouter.get_instance()
        except Exception:
            pass

    threading.Thread(target=_warmup_background, daemon=True).start()
    yield


app = FastAPI(
    title="SME Finance Copilot API",
    description="Autonomous AI CFO & Financial Participant for Small & Medium Enterprises",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

import os

# CORS configuration configurable via environment variable with local defaults
allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
origins = (
    [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
    if allowed_origins_env
    else ["http://localhost:3000", "http://127.0.0.1:3000"]
)

from api.rate_limit import TokenBucketRateLimiter

# Per-IP token bucket (60 req/min by default). Set RATE_LIMIT_PER_MINUTE=0 to disable.
# Registered before CORS so CORS stays outermost and 429 responses still carry CORS headers.
app.add_middleware(TokenBucketRateLimiter)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(health_router)
app.include_router(analyze_router)
app.include_router(actions_router)
app.include_router(underwrite_router)
app.include_router(agent_router)
app.include_router(decision_router)
app.include_router(auth_router)


from api.routes.health import get_health_status


@app.get("/health", include_in_schema=False)
async def health_alias():
    """Root health probe alias for standard container orchestrators."""
    return await get_health_status()


@app.get("/")
async def root():
    return {
        "project": "SME Finance Copilot",
        "description": "Autonomous AI CFO & Financial Participant for Small & Medium Enterprises",
        "docs": "/docs",
        "health": "/api/v1/health"
    }
