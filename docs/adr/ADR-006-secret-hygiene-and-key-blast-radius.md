# ADR-006: Secret Hygiene, Key Isolation & Blast Radius Containment

- **Status**: Accepted
- **Date**: 2026-10-14
- **Authors**: Security Guardian, Systems Architect, Lead Orchestrator
- **Scope**: Frontend zero-secret invariant, backend key isolation, IAM Workload Identity, and blast-radius minimization.

---

## 1. Threat Scenario: Stolen API Keys

An adversary attempts to extract or hijack API keys via:
1. **Frontend Inspection**: Disassembling client-side JavaScript, monitoring browser network requests, or inspecting local storage.
2. **Backend Server Compromise**: Gaining read access to server environment variables, memory dumps, or configuration files.

---

## 2. Decision: 4-Layer Key Isolation & Blast Radius Shield

```
┌────────────────────────────────────────────────────────┐
│ LAYER 1: Zero-Secret Frontend Invariant                │ -> 0 keys exist in client browser
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ LAYER 2: Blast Radius Decoupling (No Money Access)     │ -> LLM keys CANNOT move funds or read DB
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ LAYER 3: Short-Lived Ephemeral Tokens (IAM Federation) │ -> Keys auto-expire every 60 minutes
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ LAYER 4: Egress IP Pinning & Daily Hard Caps ($10/day) │ -> Stolen keys cannot be called from outside
└────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Defense Mechanics

### Layer 1: Zero-Secret Frontend Invariant
- **Rule**: The frontend code contains zero API keys, zero private keys, and zero database passwords.
- **Implementation**:
  - The client only communicates with the backend endpoint `/api/v1/chat` using short-lived HTTP-only session cookies.
  - The browser never knows whether the backend is using Gemini, OpenAI, DeepSeek, or Ollama.
  - If an attacker opens Chrome DevTools, inspects network packets, or dumps browser memory, they find 0 API keys.

### Layer 2: Blast Radius Decoupling
- **The Core Guarantee**: An LLM API key is strictly a text-generation credential.
- **What It Can Do**: Generate text tokens with the AI provider.
- **What It CANNOT Do**:
  - It has zero access to the SME's bank account.
  - It has zero access to payment transfer rails.
  - It has zero access to the PostgreSQL database.
  - It has zero access to the blockchain private keys.
- Even in the catastrophic event that an attacker steals an LLM key, the SME's money remains 100% safe.

### Layer 3: Short-Lived Ephemeral Tokens (Workload Identity Federation)
- Instead of static, permanent API strings (`sk-proj-xxxx`), enterprise deployments use cloud IAM Workload Identity:
  - The backend requests a temporary token from Google Cloud Vertex AI or AWS Bedrock.
  - The token is valid for 60 minutes and auto-rotates.
  - A stolen token expires within minutes and becomes useless.

### Layer 4: Egress IP Pinning & Hard Spend Quotas
- **IP Restriction**: API keys are locked to the backend server's static outbound IP address. If an attacker attempts to use the stolen key from their own laptop, the provider API drops the request with HTTP 403 Forbidden.
- **Hard Spend Quotas**: Account-level limits cap maximum daily spend at a fixed threshold (e.g. $10/day). If exceeded, the key auto-suspends, preventing financial loss on API bills.

### Local Ollama Mode (Zero Keys Needed)
- When running locally with Ollama, the model runs on `127.0.0.1:11434`.
- There are no API keys, no passwords, and no third-party accounts.
- Ollama binds only to localhost, rejecting all external network connections.
