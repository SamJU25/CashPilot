"""Per-request run trace: what the workstation page draws, so it must be true, ordered and content-free."""

from pathlib import Path

from services.agent import trace
from services.agent.schema import AgentChatRequest
from services.agent.supervisor import run_copilot_supervisor
from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

SAMPLES = Path(__file__).resolve().parents[2] / "data" / "samples"


def _security_check(text: str = "hello") -> None:
    DecisionEngineRegistry.get_instance().evaluate(
        DecisionRequest(
            domain=DecisionDomain.SECURITY_GATE,
            input_state={"check_prompt_security": True, "text": text},
            execution_mode="DETERMINISTIC_ONLY",
        )
    )


def test_nothing_is_recorded_outside_a_request():
    _security_check()
    with trace.recording() as events:
        pass
    assert events == []


def test_decisions_are_recorded_with_engine_and_choice():
    with trace.recording() as events:
        _security_check()
    assert len(events) == 1
    e = events[0]
    assert e.kind == "decision"
    assert e.name == "SECURITY_GATE"
    assert e.agent == "supervisor"
    assert e.detail["engine"]
    assert "choice" in e.detail and "confidence" in e.detail
    assert e.duration_ms >= 0


def test_tools_carry_the_agent_that_called_them():
    from services.agent.tools import tool_calculate_dscr

    with trace.recording() as events:
        with trace.agent("credit"):
            tool_calculate_dscr("50000", "40000")
    tools = [e for e in events if e.kind == "tool"]
    assert [t.name for t in tools] == ["tool_calculate_dscr"]
    assert tools[0].agent == "credit"
    assert tools[0].detail["ok"] == "true"


def test_events_are_in_start_order():
    with trace.recording() as events:
        _security_check()
        with trace.agent("liquidity"):
            _security_check()
    assert [e.start_ms for e in events] == sorted(e.start_ms for e in events)
    # The handoff is its own event, placed before the work done inside it.
    assert [(e.kind, e.agent) for e in events] == [("decision", "supervisor"), ("agent", "supervisor"), ("decision", "liquidity")]
    assert events[1].name == "liquidity"


def test_supervisor_returns_a_trace_that_starts_with_the_security_gate():
    resp = run_copilot_supervisor(AgentChatRequest(message="What is my cash runway?"))
    assert resp.trace, "every answer carries its trace"
    first = resp.trace[0]
    assert first.kind == "decision" and first.name == "SECURITY_GATE"


def test_trace_never_contains_statement_contents():
    csv = (SAMPLES / "deficit_statement.csv").read_text(encoding="utf-8")
    resp = run_copilot_supervisor(AgentChatRequest(message="When does my cash run short?", csv_content=csv))
    assert any(e.kind == "tool" for e in resp.trace), "a statement question runs a tool"
    dumped = " ".join(f"{e.name} {e.detail}" for e in resp.trace)
    # Descriptions and ids from the statement must never reach the client through the trace.
    for line in csv.splitlines()[1:6]:
        for field in line.split(","):
            if len(field) > 8 and not field.replace(".", "").replace("-", "").isdigit():
                assert field not in dumped
