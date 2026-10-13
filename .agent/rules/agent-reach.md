---
trigger: always_on
description: Auto-apply Agent Reach multi-platform internet routing, search, and reading standards.
---

# Agent Reach Internet Capability Router

Scope: Antigravity and Claude coding assistants.
Source: https://github.com/Panniantong/Agent-Reach

## 1. Capability Routing Invariant
When the user requests internet research, web page extraction, repository inspection, video transcription, or social community lookup:
- Use Agent Reach routing and upstream tools rather than raw browser scraping or inventing ad-hoc scrapers.
- Use zero-config channels directly:
  - Web pages / articles: Jina Reader (`curl -s "https://r.jina.ai/<URL>"`)
  - Video subtitles & transcripts: `yt-dlp` for YouTube
  - Repositories & code: GitHub CLI (`gh search repos`, `gh repo view`)
  - RSS/Atom: `feedparser`
  - Tech & news topics: V2EX API (`https://www.v2ex.com/api/topics/hot.json`)
  - Bilibili: search via API / `bili-cli`
- For multi-backend or login-backed channels (Twitter/X, Reddit, XiaoHongShu, Facebook, Instagram, LinkedIn, Boss Zhipin):
  - Run `agent-reach doctor --json` first to confirm `active_backend`.
  - Follow the retry chains in `agent-reach/references/`.
  - Never guess command flags or forge fake authentication cookies.

## 2. Safety & Workspace Invariant
- **Strictly Read-Only:** Only fetch, search, and read internet content. Do not automate write actions (posting, commenting, liking, following, or profile mutations).
- **Workspace Hygiene:** Never write scratch, media, or temporary files into the project repository. Use Windows `%TEMP%` or `C:\Users\Sam\.agent-reach\`.
- **Runtime Isolation:** Never commit Agent Reach configuration, tokens, or history into project configuration files.
