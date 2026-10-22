"""
FastAPI Main Application Entrypoint.
Configures CORS, Security Headers, and Router Mounts.
Aligns with docs/system.md Section 4 and docs/security.md Section 4.
"""

import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path


def _load_env_files() -> None:
    """Reads .env.local then .env so a plain `uvicorn` start shares the Next.js server's tenant keys.
    Real environment variables win. Skipped under pytest, whose tests set their own environment."""
    if "pytest" in sys.modules:
        return
    root = Path(__file__).resolve().parent.parent
    for name in (".env.local", ".env"):
        path = root / name
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Before the routers import: some read their settings at import time.
_load_env_files()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes.health import router as health_router
from api.routes.analyze import router as analyze_router
from api.routes.actions import router as actions_router
from api.routes.underwrite import router as underwrite_router
from api.routes.agent import router as agent_router
from api.routes.decision import router as decision_router
from api.routes.auth import router as auth_router
from api.routes.sentinel import router as sentinel_router
from api.routes.plaid import router as plaid_router

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
        # Preload default local GGUF model if downloaded; spares the user's first query that wait.
        if os.getenv("LOCAL_PRELOAD_MODEL", "1") == "1" and "pytest" not in sys.modules:
            try:
                from services.agent.local_transformers import LocalTransformersEngine

                engine = LocalTransformersEngine.get_instance()
                if engine.is_available():
                    engine._ensure_loaded()
            except Exception:
                pass

    threading.Thread(target=_warmup_background, daemon=True).start()

    from services.sentinel.sentinel_daemon import sentinel_daemon

    if "pytest" not in sys.modules and os.getenv("SENTINEL_DAEMON_ENABLED", "1") == "1":
        sentinel_daemon.start()

    yield

    if "pytest" not in sys.modules:
        sentinel_daemon.stop()


app = FastAPI(
    title="CashPilot API",
    description="Autonomous AI CFO & Financial Participant for Small & Medium Enterprises",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Deployments list their origins in ALLOWED_ORIGINS. Without it, any local port is allowed: `next dev`
# moves to 3001+ when 3000 is taken, and a blocked origin shows the whole app as offline.
allowed_origins_env = os.getenv("ALLOWED_ORIGINS")
origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()] if allowed_origins_env else []
origin_regex = None if allowed_origins_env else r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"

from api.rate_limit import TokenBucketRateLimiter

# Per-IP token bucket (60 req/min by default). Set RATE_LIMIT_PER_MINUTE=0 to disable.
# Registered before CORS so CORS stays outermost and 429 responses still carry CORS headers.
app.add_middleware(TokenBucketRateLimiter)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=origin_regex,
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
app.include_router(sentinel_router)
app.include_router(plaid_router)


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
