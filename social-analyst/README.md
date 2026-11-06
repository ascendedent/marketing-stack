# Social Analyst

An agent-agnostic workspace that turns Claude, GPT/Codex or Grok into a social media analyst for any
set of owned accounts:

- **Onboards** an account: interviews the owner, connects Buffer channels, pulls the public
  profile and post history, breaks down top/bottom videos, infers voice/audience/pillars, and writes
  a profile brief.
- **Analyzes** performance: syncs per-post metrics from Buffer into a local store and produces a
  deterministic pattern report (lift by weekday, hour, format, media, length, hooks, hashtags; trend;
  top/bottom posts) that every model reads the same way.
- **Watches videos**: downloads TikTok/Reels/Shorts/X/YouTube and gets a structured Gemini breakdown
  (hook, scenes with timestamps, transcript, pacing, retention risks, improvements).
- **Acts**: plans content from the evidence and files it in Buffer as Ideas/drafts for approval.
- **Goes deeper where Buffer stops** (each optional, each with a guide in `docs/`):
  YouTube (watch time, retention, thumbnail impressions + CTR, traffic, demographics) ·
  Instagram (reach, saves, shares, Reels watch time/completion, demographics) ·
  Threads (views, shares, demographics) · X (link/profile clicks, bookmarks) ·
  LinkedIn (member post saves/sends/clicks, Page follower demographics) ·
  TikTok Studio exports (watch time, completion).
- **Remembers**: per-account `learnings.md` so the next session, on any model, starts where the last stopped.

> **Only use claude.ai, ChatGPT or grok.com in the browser?** Use the **[web edition](web/README.md)** —
> download one zip, upload it, connect Buffer. No terminal needed (lighter: no daily history or deep connectors).

## Quick start

Open your agent in this folder and say hi:

```bash
cd social-analyst
claude            # or: codex | grok   (or scripts/agent.sh <name> once .env exists)
```

That's it. At session start the agent runs `scripts/session_start.sh` (Claude Code does it
automatically through a SessionStart hook; Codex and Grok are told to by `AGENTS.md`). It sees what's
missing and walks you through setup from the chat with the **setup** skill:

1. installs prerequisites (uv, Python deps; asks before installing ffmpeg),
2. helps you create/connect Buffer if needed (**[docs/buffer-setup.md](docs/buffer-setup.md)**),
3. opens a **local form** in your browser for API keys — they go straight into `.env`, never into the chat,
4. verifies Buffer and Gemini live (and self-tests the video pipeline on a 3-second synthetic clip),
5. creates your first account and onboards it (profile, history, video breakdowns, voice, KPIs),
6. optionally connects deep analytics — [YouTube](docs/connect-youtube.md), [Instagram](docs/connect-instagram.md),
   [Threads](docs/connect-threads.md), [X](docs/connect-x.md), [LinkedIn](docs/connect-linkedin.md),
   [TikTok exports](docs/connect-tiktok.md),
7. optionally schedules the daily metrics sync.

Check progress any time with `uv run sma setup status`. Manual route: `uv sync`, `uv run sma setup init`,
`uv run sma setup keys`, then ask the agent to onboard an account.

Once `.env` exists, prefer `scripts/agent.sh claude|codex|grok`: it exports `.env` so the Buffer/Apify
MCP servers can authenticate, and regenerates the Codex/Grok MCP config.

## How it works with each agent

| | instructions | skills | MCP servers |
|---|---|---|---|
| Claude Code | `CLAUDE.md` → imports `AGENTS.md` | `.claude/skills` (symlink) | `.mcp.json` |
| Codex CLI | `AGENTS.md` | `.agents/skills` | `.codex/config.toml` (generated; trust the folder) |
| Grok CLI | `AGENTS.md` | `.agents/skills` | `.grok/config.toml` (generated) |
| Chat apps (Claude.ai, ChatGPT, Grok web) | paste `AGENTS.md` / use a project | — | add `uv run sma-mcp` locally or the hosted Buffer MCP |

Everything an agent does goes through one CLI (`uv run sma …`) or the identical local MCP server
(`uv run sma-mcp`), so results don't depend on which model is driving.

## Layout
See the bottom of [AGENTS.md](AGENTS.md). Key folders: `src/sma/` (toolkit), `.agents/skills/`
(workflows), `knowledge/` (frameworks & benchmarks), `docs/` (setup tutorial, learnings, sources),
`accounts/<slug>/` (per-account brief, learnings, reports, video breakdowns — gitignored).

## Keeping data fresh
`uv run sma setup schedule` installs a daily `sma sync` (systemd user timer, launchd, or a cron line).
Each run pulls Buffer plus every connected first-party source and stores a dated metrics
snapshot per post, so growth over time becomes analyzable. TikTok Studio exports are imported by hand.

## Tests
`uv run pytest -q` — offline; connectors are exercised against faked API responses.

## Reference repos
`scripts/fetch_reference.sh` clones the evaluated third-party repos into `reference/` (read-only).
What was taken from each is in [docs/sources.md](docs/sources.md).
