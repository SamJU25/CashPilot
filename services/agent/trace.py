"""
Per-request run trace for the workstation page: which agent ran, which tools it called, which
decisions the engine made and which knowledge cards were read, with timings.

Only names, identifiers, outcomes and timings are recorded, never statement rows or message text,
because the trace is returned to the client. Recording is off unless a request opens it, and each
request (thread or task) gets its own list through a context variable.
"""

from __future__ import annotations

import functools
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Dict, Iterator, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

TraceKind = Literal["agent", "tool", "decision", "card"]

# A detail value is clipped so a long rationale cannot carry figures or text in bulk.
_MAX_DETAIL = 160


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: TraceKind
    name: str
    agent: str = "supervisor"
    start_ms: float
    duration_ms: float
    detail: Dict[str, str] = Field(default_factory=dict)


_events: ContextVar[Optional[List[TraceEvent]]] = ContextVar("trace_events", default=None)
_origin: ContextVar[float] = ContextVar("trace_origin", default=0.0)
_agent: ContextVar[str] = ContextVar("trace_agent", default="supervisor")


def _now_ms() -> float:
    return (time.perf_counter() - _origin.get()) * 1000.0


@contextmanager
def recording() -> Iterator[List[TraceEvent]]:
    """Collects every event recorded inside the block into the yielded list."""
    events: List[TraceEvent] = []
    t_events = _events.set(events)
    t_origin = _origin.set(time.perf_counter())
    t_agent = _agent.set("supervisor")
    try:
        yield events
    finally:
        _events.reset(t_events)
        _origin.reset(t_origin)
        _agent.reset(t_agent)


def active() -> bool:
    return _events.get() is not None


def record(kind: TraceKind, name: str, start_ms: float, duration_ms: float, **detail: Any) -> None:
    events = _events.get()
    if events is None:
        return
    clean = {k: str(v)[:_MAX_DETAIL] for k, v in detail.items() if v is not None}
    events.append(
        TraceEvent(kind=kind, name=name, agent=_agent.get(), start_ms=round(start_ms, 3), duration_ms=round(max(0.0, duration_ms), 3), detail=clean)
    )


@contextmanager
def agent(agent_id: str) -> Iterator[None]:
    """Attributes everything inside the block to a subagent and records the handoff itself."""
    if not active():
        yield
        return
    start = _now_ms()
    token = _agent.set(agent_id)
    try:
        yield
    finally:
        _agent.reset(token)
        events = _events.get()
        if events is not None:
            # The handoff opens before its tools, so it is placed at its start time.
            events.insert(
                next((i for i, e in enumerate(events) if e.start_ms >= start), len(events)),
                TraceEvent(kind="agent", name=agent_id, agent="supervisor", start_ms=round(start, 3), duration_ms=round(_now_ms() - start, 3)),
            )


def traced_tool(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Records a tool call: its function name, how long it took and whether it raised."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not active():
            return fn(*args, **kwargs)
        start = _now_ms()
        ok = False
        try:
            result = fn(*args, **kwargs)
            ok = True
            return result
        finally:
            record("tool", fn.__name__, start, _now_ms() - start, ok=str(ok).lower())

    wrapper.__traced__ = True  # type: ignore[attr-defined]
    return wrapper


def traced_agent(agent_id: str) -> Callable[[type], type]:
    """Class decorator: every public handle_* method runs inside that subagent's span."""

    def decorate(cls: type) -> type:
        for name, member in list(vars(cls).items()):
            if not name.startswith("handle_"):
                continue
            kind = type(member)
            func = member.__func__ if isinstance(member, (classmethod, staticmethod)) else member

            def make(f: Callable[..., Any]) -> Callable[..., Any]:
                @functools.wraps(f)
                def wrapped(*args: Any, **kwargs: Any) -> Any:
                    with agent(agent_id):
                        return f(*args, **kwargs)

                return wrapped

            wrapped = make(func)
            setattr(cls, name, kind(wrapped) if kind in (classmethod, staticmethod) else wrapped)
        return cls

    return decorate


def now_ms() -> float:
    """Milliseconds since the request's recording began; for callers that time a step themselves."""
    return _now_ms()
