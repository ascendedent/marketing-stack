# Social Analyst — web edition

The same analyst for people who only use the chat apps — **claude.ai**, **ChatGPT**, **grok.com** —
no terminal, no install. Pick your app, download one zip, follow its 5-minute guide:

| app | download | guide |
|---|---|---|
| Claude | [`dist/social-analyst-claude.zip`](dist/social-analyst-claude.zip) | [claude/README.md](claude/README.md) |
| ChatGPT | [`dist/social-analyst-chatgpt.zip`](dist/social-analyst-chatgpt.zip) | [chatgpt/README.md](chatgpt/README.md) |
| Grok | [`dist/social-analyst-grok.zip`](dist/social-analyst-grok.zip) | [grok/README.md](grok/README.md) |

(On GitHub: open the zip link → **Download raw file**.)

## What you get
- **Onboarding**: the analyst interviews you, reads your history, and writes an account profile
  (purpose, voice, audience, content pillars, KPI) that you keep in your Project.
- **Performance reviews**: from your **Buffer** connection or analytics **exports** you upload
  (Buffer, LinkedIn, Meta Business Suite, TikTok Studio, YouTube Studio, X). A bundled script
  (`report.py`) computes the numbers the same way every time — medians, per-channel "lift", sample
  sizes — so the model interprets instead of guessing.
- **Video breakdowns** via a ready-made prompt for Gemini (free), which the analyst then interprets.
- **Content plans and drafts**, filed in Buffer as Ideas/drafts for your approval (never published
  on its own), or handed back as copy-ready text.

## Web vs full version
| | web edition | full version (repo root, runs on your computer) |
|---|---|---|
| Setup | upload files, connect Buffer | terminal agent (Claude Code / Codex / Grok CLI), guided setup |
| Data | Buffer connector or uploaded exports, per conversation | Buffer API synced daily into a local history |
| Metrics depth | what Buffer/exports give | + YouTube, Instagram, Threads, X, LinkedIn connectors, TikTok imports |
| Video | you run the Gemini prompt | downloads + Gemini analysis automatically |
| Memory | profile + learnings saved as Project files | per-account files, updated by the agent |

One catch on all three apps: Buffer only returns post metrics to personal API keys, and chat-app
connectors sign in with OAuth — so the connector may show your posts without numbers. When that
happens, the analyst switches to exports (it tells you exactly where to click per platform).

## Maintainers
Sources: `shared/` (instructions, workflows, report script, templates) + `../knowledge/` (frameworks).
Rebuild after editing: `python3 web/build.py` (tests fail if `dist/` is stale).
