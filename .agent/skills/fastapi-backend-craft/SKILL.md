---
name: fastapi-backend-craft
description: "Best practices for building high-performance asynchronous FastAPI backends for the SME Finance Copilot. Use when designing REST APIs, Pydantic v2 validation models, dependency injection, async database sessions, and deterministic calculation endpoints."
---

# FastAPI Backend Craft for SME Finance Copilot

Production patterns for building resilient, type-safe, asynchronous FastAPI backend microservices.

## 1. Architecture & Layering

Maintain strict separation of concerns across four distinct layers:

```
app/
├── api/v1/          # Path operations, routers, dependency injection
│   ├── routers/     # cashflow.py, underwriting.py, invoices.py, security.py
│   └── deps.py      # get_db, get_current_user, require_tier3_auth
├── core/            # Config, security, database session managers
│   ├── config.py    # Pydantic BaseSettings (JWT, DB_URL, REDIS_URL)
│   └── database.py  # AsyncEngine, async_sessionmaker
├── models/          # SQLAlchemy 2.0 ORM database models
├── schemas/         # Pydantic v2 request/response schemas
└── services/        # Deterministic business logic & financial calculations
    ├── cashflow.py  # Pure decimal math, zero floating point
    └── underwriting.py
```

## 2. Invariants & Rules

- **Deterministic Math Isolation**: Financial calculations (DSCR, Runway, Burn Rate, APR) must reside in `services/` and use Python's `decimal.Decimal`. Never perform calculations directly in route handlers or allow LLM free-text math.
- **Pydantic v2 Validation**: Use strict type annotations, `Field(description=..., ge=0)`, and `@model_validator(mode='after')` for cross-field consistency.
- **Async Database Sessions**: Use `async with async_session() as session:` with explicit commit and rollback boundaries.
- **Global Error Handling**: Catch domain exceptions and map them to standard RFC 7807 problem details JSON.
