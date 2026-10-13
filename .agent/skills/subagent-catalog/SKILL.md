---
name: subagent-catalog
description: "Browse, search, and fetch subagents dynamically from the VoltAgent awesome-claude-code-subagents 161+ agent collection. Use when looking for additional niche language specialists, cloud providers, or tooling agents on demand."
---

# Subagent Catalog Skill

This skill allows on-demand searching and fetching of specialized subagents from the 161+ agent repository (`https://github.com/VoltAgent/awesome-claude-code-subagents`).

## How to Use

When the user needs an additional specialized agent (e.g. for Terraform, Kubernetes, Rust, Elixir, Flutter, etc.):

1. **Search Catalog**:
   Search for matching agents by domain or keyword in the local cache or upstream repository.

2. **Fetch and Install**:
   Fetch the agent definition and install it into `F:\SME Finance Copilot\.agent\agents\<category>\` with `model: inherit`.

3. **Verify Frontmatter**:
   Ensure the YAML frontmatter contains unambiguous `name:` and `description:` triggers so it operates smoothly without collisions.
