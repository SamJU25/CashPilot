# ADR-007: Backend Defense-in-Depth & Container Hardening

- **Status**: Accepted
- **Date**: 2026-10-14
- **Authors**: Security Guardian, Systems Architect, Lead Orchestrator
- **Scope**: FastAPI application server, PostgreSQL network topology, container runtime hardening, and OS privileges.

---

## 1. Threat Scenario: Direct Backend Attacks

Adversaries attempt to breach the backend via:
1. **Network Reconnaissance & DDoS**: Scanning ports, flooding endpoints, or exploiting exposed database ports.
2. **Application-Layer Exploits**: Remote Code Execution (RCE), deserialization bugs, or parameter pollution.
3. **Privilege Escalation**: Breaking out of a compromised container to compromise the host operating system.
4. **Data Interception**: Snooping database traffic or executing unauthorized SQL commands.

---

## 2. Decision: 5-Ring Backend Defense Architecture

```
Internet Request
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ RING 1: Network Perimeter & Private VPC                │ -> Port 5432 has NO public IP; Rate limiting
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ RING 2: Strict Application Gateway (FastAPI + Rust)    │ -> Pydantic Rust parser drops malformed data (422)
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ RING 3: Asymmetric Auth & RBAC (RS256 JWT)            │ -> HTTP-only cookies; tenant extracted from token
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ RING 4: Database Defense (Least Privilege + RLS)       │ -> Unprivileged DB role; Kernel-enforced RLS
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ RING 5: OS & Container Hardening (Rootless + Read-Only)│ -> Non-root user; read-only rootfs; dropped caps
└────────────────────────────────────────────────────────┘
```

---

## 3. Ring-by-Ring Implementation Specifications

### Ring 1: Network Perimeter & Private VPC Isolation
- **No Public Database IP**: The PostgreSQL server and FISCO BCOS node run inside an isolated internal subnet (`10.0.2.0/24`). Public internet traffic cannot route to port 5432. Only the FastAPI backend service inside the private network can connect.
- **Rate Limiting**: Nginx/Cloudflare enforces token-bucket rate limiting (60 requests/minute per IP) to mitigate brute-force and DDoS attempts.

### Ring 2: Strict Application Gateway (FastAPI + Pydantic v2)
- **Rust-Compiled Strict Parsing**: All input schemas set `model_config = ConfigDict(extra="forbid", strict=True)`. Any unexpected fields or invalid types trigger an immediate HTTP 422 before application logic executes.
- **Strict CORS & Security Headers**:
  - `Access-Control-Allow-Origin` locked strictly to the production frontend domain.
  - Security headers enforced on every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Strict-Transport-Security: max-age=31536000`.

### Ring 3: Asymmetric Authentication & RBAC
- **RS256 Cryptographic Tokens**: JWTs are signed using RSA-2048 / Ed25519 private keys. The backend validates tokens using the public key.
- **HTTP-Only, SameSite=Strict Cookies**: Authentication tokens are not stored in browser `localStorage`, making them immune to extraction via Cross-Site Scripting (XSS).
- **Tenant Context Binding**: The backend extracts `tenant_id` exclusively from verified token claims.

### Ring 4: Database Least Privilege & Kernel RLS
- **Unprivileged Database Role**: The application connects using a restricted user (`copilot_app`) that has zero privileges to `DROP TABLE`, `ALTER TABLE`, or access system catalogs.
- **Kernel-Enforced RLS**: Every query runs after setting `SET LOCAL app.current_tenant_id = '...'`. The database engine guarantees 0-row visibility across distinct tenants.
- **Binary Parameterized Protocol**: `asyncpg` passes SQL statements and data in separate binary protocol packets, rendering SQL injection syntactically impossible.

### Ring 5: Container Hardening & Immutability
- **Rootless Container Execution**: The Docker container runs under unprivileged UID `10001` (`USER appuser`), never as root (`UID 0`).
- **Read-Only Root Filesystem**: The container is launched with `--read-only`. An attacker achieving arbitrary code execution cannot write malicious executables or modify system binaries.
- **Linux Capability Stripping**: All Linux kernel capabilities are dropped (`--cap-drop=ALL`). The container cannot mount filesystems, manipulate network routes, or snoop on other processes.
