# ADR-004: LLM Gateway, Model Selection & Structured Output Contract

- **Status**: Accepted
- **Date**: 2026-10-14
- **Authors**: LLM Architect, Systems Architect, Lead Orchestrator
- **Scope**: LLM client abstraction, provider routing, structured output enforcement, and test mocking.

---

## 1. Context & Objective

The SME Finance Copilot requires an LLM reasoning engine (the "Brain") to interpret natural language questions, synthesize complex financial diagnostic data, and draft structured action intents for human review.

Key Constraints:
1. Provider Independence: Must switch between Google Gemini, OpenAI, Claude, DeepSeek, or local Ollama via environment variables.
2. Zero Hallucination of Data: The LLM must reason over verified deterministic numbers computed by Python, not invent numbers.
3. Strict Output Typing: Responses must conform to Pydantic v2 schemas; unstructured raw text cannot trigger downstream workflows.
4. Offline Testability: Unit and integration tests must run without incurring API token costs or network latency.

---

## 2. Decision: LiteLLM + Instructor Architecture

```
[ SME User Query ] ──> [ Python Pre-Calculator (Deterministic Metrics) ]
                                   │
                                   ▼
                      [ System Prompt Assembler ]
                      (Injects verified numbers + XML guardrails)
                                   │
                                   ▼
                       [ LiteLLM Unified Router ]
                      (Routes to Gemini / GPT-4o / DeepSeek / Ollama)
                                   │
                                   ▼
                       [ Instructor Structured Parser ]
                      (Enforces CopilotResponse Pydantic Schema)
                                   │
                                   ▼
               ┌───────────────────┴───────────────────┐
               ▼                                       ▼
  [ Conversational Text ]               [ ActionIntentDraft (Staged) ]
  (Monospace Tabular UI)                (Awaiting owner's prepare)
```

---

## 3. Implementation Blueprint

### Configuration via `.env`
```bash
# Model selection: 'gemini/gemini-2.0-flash', 'gpt-4o', 'deepseek/deepseek-chat', or 'ollama/llama3.1:8b'
LLM_MODEL=gemini/gemini-2.0-flash
GEMINI_API_KEY=your_gemini_api_key_here
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=1024
```

### Unified Client Gateway (`services/llm/gateway.py`)
```python
import os
import instructor
from litellm import completion
from pydantic import BaseModel, Field
from typing import Optional

# Patch LiteLLM with Instructor for strict Pydantic structured output
client = instructor.from_litellm(completion)

class ActionIntentDraft(BaseModel):
    action_type: str = Field(description="STAGING action: FACTOR_INVOICE, DRAW_CREDIT_LINE, or NONE")
    amount_cents: int = Field(default=0, ge=0)
    target_identifier: str = Field(default="", description="Invoice ID or Facility ID")
    justification: str = Field(description="Mathematical explanation for the proposal")

class CopilotResponse(BaseModel):
    conversational_explanation: str = Field(description="Clear, jargon-free explanation for the business owner")
    urgency_level: str = Field(description="LOW, MEDIUM, or CRITICAL")
    staged_intent: Optional[ActionIntentDraft] = None
```

### Deterministic Context Injection (Brain Protocol)
Before invoking the LLM, the backend calculates the metrics:
```python
def generate_copilot_advice(user_question: str, verified_metrics: dict) -> CopilotResponse:
    system_prompt = f"""
    You are the SME Finance Copilot.
    VERIFIED FINANCIAL FACTS (COMPUTED BY BACKEND - DO NOT ALTER):
    - Current Cash Balance: ${verified_metrics['cash_balance']}
    - Net Daily Burn: ${verified_metrics['daily_burn']}
    - Exact Runway: {verified_metrics['runway_days']} days
    - DSCR: {verified_metrics['dscr']}x
    
    RULES:
    1. Base all answers strictly on the verified facts above.
    2. Never invent numbers.
    3. If cash runway is under 30 days, propose a financing ActionIntentDraft.
    """
    
    response = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash"),
        response_model=CopilotResponse,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_question}
        ],
        temperature=0.1
    )
    return response
```

---

## 4. Test Mocking & Deterministic Verification

For automated testing (`pytest tests/`), a `MockLLMGateway` returns canned, schema-valid `CopilotResponse` fixtures:
- No internet access required during tests.
- 0 token expense.
- 100% deterministic test execution in milliseconds.
