---
name: setup
description: Drive the whole first-run setup with the owner from inside the chat — install prerequisites, create .env, collect API keys through a local form (never through chat), verify Buffer and Gemini live, connect optional deep analytics (YouTube, Instagram, TikTok export), create and onboard the first account, and schedule the daily sync. Use at the start of any session where `scripts/session_start.sh` / `sma setup status` reports pending steps, or when the owner says "set this up", "get started", "connect my accounts" or "add Buffer".
---

# Setup (agent-driven)

The checklist is the source of truth: `uv run sma setup status` (add `--live` to verify keys against the
APIs). It returns ordered `steps` and one `next_step`. Loop: **do next_step → re-run status → repeat**
until `complete` is true and the optional steps are done or declined.

## How to run the conversation
- Open with one line on what's missing and ask to start. Don't dump the checklist.
- Do every step you can yourself (commands, files, configs). The owner only does what needs their
  hands: creating accounts, clicking OAuth consent, pasting keys into the local form, exporting files.
- One owner action at a time, with the exact link/button names, then wait for "done".
- Ask before anything that installs software, uses sudo, spends money, or schedules jobs.
- **Never ask for keys in chat.** Use the form (below). If the owner pastes a key into chat anyway,
  write it with `printf '%s' '<key>' | uv run sma setup set-key NAME`, tell them it's now in the
  transcript, and suggest rotating it later.

## Step guide (in checklist order)

**0. Prerequisites** (session_start.sh reports these before the toolkit can run)
- `uv` missing → ask, then `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS `brew install uv`).
- `uv sync` (first run installs deps; ~1 min).
- `tools` ✗ → ffmpeg: `sudo dnf install ffmpeg` / `sudo apt install ffmpeg` / `brew install ffmpeg` — ask first;
  if they can't sudo, they run it themselves.

**1. env_file** → `uv run sma setup init` (creates `.env`, data dirs, Codex/Grok MCP configs).

**2. Short intake** — ask all at once, so later steps only cover what they need:
1. Do you already have a Buffer account with your social channels connected? (yes / some / no)
2. Which platforms matter most? (Instagram, TikTok, YouTube, LinkedIn, X, Threads, Facebook, Pinterest…)
3. Do you want video breakdowns (needs a free Gemini key)? *(default yes)*
4. For your main platform, do you want deep analytics beyond Buffer (YouTube watch time/retention,
   Instagram saves/reach/demographics, TikTok Studio exports)? *(can be done later)*

**3. buffer_account**
- No Buffer / channels not connected → walk `docs/buffer-setup.md` §1–4 one step at a time
  (sign up → plan → prepare each platform per the §2 table → connect channels → posting schedule).
- Then: `uv run sma setup keys --only BUFFER_API_KEY` — prints a local URL and opens the browser.
  Tell the owner: "A form opened at <url>. Paste the key from publish.buffer.com/settings/api → Save.
  I can't see what you paste." The command waits up to 15 min and returns which keys were saved and
  whether they validated (channel list). Several Buffer logins? Add `BUFFER_API_KEY_<NAME>` via
  `--only BUFFER_API_KEY_CLIENTA` (any name).
- Validation failed → re-check §5 (personal key from the new API, not a legacy token).

**4. gemini_key** (if they want video)
- `uv run sma setup keys --only GEMINI_API_KEY` (key: https://aistudio.google.com/apikey — free tier works).
- Then `uv run sma setup gemini --fix --test`: checks the configured model exists (switches
  `GEMINI_VIDEO_MODEL` to the best available Flash model if not) and runs a 3-second synthetic clip
  through the full pipeline. Report the model and that the test passed.
- Several keys at once is fine: `--only BUFFER_API_KEY,GEMINI_API_KEY`.

**5. MCP for this agent** (optional but nice)
- `python3 scripts/sync_mcp.py`. Tell the owner to restart the agent via `scripts/agent.sh <claude|codex|grok>`
  so `.env` is exported for the MCP servers (Claude: approve the project MCP servers when asked;
  Codex: trust the folder). Skip if they'd rather not restart now — the `sma` CLI covers everything.

**6. first_account** → ask which account (or brand/client) to start with and a short slug, then
hand over to the **onboard-account** skill. It links Buffer channels, syncs, discovers, breaks down
videos, infers voice/audience, proposes KPIs and marks the account active.

**7. Deep analytics (optional, per platform from the intake)**
- YouTube → walk `docs/connect-youtube.md` (Google Cloud project, 2 APIs, consent screen, Desktop
  OAuth client), keys via `uv run sma setup keys --only GOOGLE_OAUTH_CLIENT_ID,GOOGLE_OAUTH_CLIENT_SECRET`,
  then `uv run sma connect youtube <slug>` (opens Google consent; owner clicks Allow), then `uv run sma sync <slug>`.
- Instagram → walk `docs/connect-instagram.md`, key via `--only INSTAGRAM_ACCESS_TOKEN`, then
  `uv run sma connect instagram <slug>` and `uv run sma sync <slug>`.
- TikTok → `docs/connect-tiktok.md`: owner exports from TikTok Studio, tells you the file path;
  `uv run sma import tiktok <slug> <path>`.
- Threads → `docs/connect-threads.md`, key `THREADS_ACCESS_TOKEN`, `uv run sma connect threads <slug>`.
- X → `docs/connect-x.md` (**paid API — say so and get a yes first**), keys `X_CLIENT_ID,X_CLIENT_SECRET`,
  `uv run sma connect x <slug>` (browser consent).
- LinkedIn → `docs/connect-linkedin.md` (**needs LinkedIn to approve Community Management API access;
  set expectations — days to weeks, businesses only**), keys `LINKEDIN_CLIENT_ID,LINKEDIN_CLIENT_SECRET`,
  `uv run sma connect linkedin <slug> --mode member` and/or `--mode org --org-id <id>`.
- After any connect: `uv run sma sync <slug>` and show what arrived (`sma account-metrics <slug>`).

**8. daily_sync** → ask "Refresh metrics automatically every morning?" then
`uv run sma setup schedule --at 06:30` (systemd user timer on Linux, launchd on macOS, cron line otherwise).

**9. Finish** → `uv run sma setup status --live`. Summarize in ≤6 lines: what's connected, what's
optional and skipped, and 2–3 things they can ask for now ("weekly performance review",
"break down our top 5 videos", "plan next week's posts").

## Troubleshooting quick map
| symptom | fix |
|---|---|
| form never opened | give the printed `form_url`; it's on 127.0.0.1 only; re-run with a longer `--timeout` |
| form timed out | re-run `sma setup keys --only …` |
| Buffer `Unauthorized` | legacy/wrong key → docs/buffer-setup.md §5 |
| 0 channels | channels not connected in that Buffer login, or wrong login |
| Gemini 400 invalid key | re-create at aistudio.google.com/apikey |
| Gemini model 404 | `sma setup gemini --fix` |
| YouTube refresh fails after 7 days | OAuth app still in Testing → publish it (connect-youtube §4), reconnect |
| IG `insufficient permission` | token lacks `instagram_business_manage_insights` → regenerate (connect-instagram §3) |
| OAuth "redirect_uri mismatch" (X/LinkedIn) | register exactly `http://localhost:8765/callback` (or set `SMA_OAUTH_PORT` and register that) |
| port 8765 busy | `SMA_OAUTH_PORT=8899` in `.env`, update the app's redirect URL |
| LinkedIn 403 on analytics | app not approved for Community Management API yet |
| YouTube impressions missing | reporting job is < 48h old; they arrive on a later sync |
