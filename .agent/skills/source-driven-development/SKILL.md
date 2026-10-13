---
name: source-driven-development
description: Grounds every implementation decision in official documentation. Use when you want to verify an approach against the official docs before implementing it, or when you want authoritative, source-cited code free from outdated patterns. Use when building with any framework or library where correctness matters.
---

# Source-Driven Development

## Overview
Every framework-specific code decision must be backed by official documentation. Don't implement from memory — verify, cite, and let the user see your sources. Training data goes stale, APIs get deprecated, best practices evolve. This skill ensures the user gets code they can trust because every pattern traces back to an authoritative source they can check.

## When to Use
- The user wants code that follows current best practices for a given framework.
- Building boilerplate, starter code, or patterns that will be copied across a project.
- The user explicitly asks for documented, verified, or "correct" implementation.
- Implementing features where the framework's recommended approach matters (forms, routing, data fetching, state management, auth).
- Reviewing or improving code that uses framework-specific patterns.
- Any time you are about to write framework-specific code from memory.

**When NOT to use:**
- Correctness does not depend on a specific version (renaming variables, fixing typos, moving files).
- Pure logic that works the same across all versions (loops, conditionals, data structures).
- The user explicitly wants speed over verification ("just do it quickly").

## The Process

```
DETECT ──→ FETCH ──→ IMPLEMENT ──→ CITE
  │          │           │            │
  ▼          ▼           ▼            ▼
 What       Get the    Follow the   Show your
 stack?     relevant   documented   sources
            docs       patterns
```

### Step 1: Detect Stack and Versions
Read the project's dependency file to identify exact versions:
`package.json`, `requirements.txt`, `pyproject.toml`, `go.mod`, `Cargo.toml`.
State what you found explicitly before implementing. If versions are missing, ask the user.

### Step 2: Fetch Official Documentation
Fetch the specific documentation page for the feature you're implementing via Agent Reach (`Jina Reader` or official docs). Not the homepage — the exact reference page.

**Source hierarchy (in order of authority):**
1. Official documentation (docs.python.org, fastapi.tiangolo.com, react.dev, pydantic.dev)
2. Official blog / changelog / release notes
3. Web standards references (MDN, W3C)

**Never cite as primary sources:**
- Random blog posts, outdated tutorials, or unverified memory.

### Step 3: Implement According to Verified Specs
Adhere strictly to the verified syntax, avoiding deprecated arguments or obsolete patterns.

### Step 4: Cite Your Sources
Include the verified source URL in code comments or briefing notes.
