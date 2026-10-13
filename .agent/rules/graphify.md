---
trigger: always_on
description: Consult the graphify knowledge graph at graphify-out/ for codebase questions, and automatically sync on every project update, edit, or file creation.
---

## graphify

This project has a graphify knowledge graph at graphify-out/.
Scope: Antigravity and Claude coding assistants.

Rules:
- For codebase or architecture questions, when `graphify-out/graph.json` exists, first run `graphify query "<question>"` (CLI) or `query_graph` (MCP). Use `graphify path "<A>" "<B>"` / `shortest_path` for relationships and `graphify explain "<concept>"` / `get_node` for focused concepts.
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- Automatically apply on every project update, edit, or file creation: after modifying or creating code files, run `cmd /c "python -m graphify update ."` to keep the graph current (AST-only, 0 token cost). If files were deleted or renamed, pass `--force`.
