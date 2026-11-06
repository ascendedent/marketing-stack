---
name: onboard-account
description: Set up a new social account for analysis — interview the owner about purpose and goals, connect its Buffer channels, pull its public profile and post history, analyze its best videos, infer voice/audience/pillars, and write accounts/<slug>/profile.md. Use when adding an account, when an account's status is "onboarding", or when asked to "learn about", "get to know", or "audit from scratch" a social profile.
---

# Onboard an account

Goal: by the end, `accounts/<slug>/profile.md` is a brief any model could work from, every line marked
✅ (owner confirmed) or 🔎 (inferred, with source), and `account.json` has `status: "active"`.

Work in this order. Gather evidence before asking questions, so the questions are sharp and few.

## 1. Scaffold
```bash
uv run sma setup status --live    # need a working Buffer login; if not, run the `setup` skill first
uv run sma account new <slug> --name "<Display Name>"
```

## 2. Minimum intake (ask once, all together)
Ask only what you cannot discover:
1. Profile URLs/handles for every platform this account uses (and which are primary).
2. In one sentence: what is this account *for*? (sales, leads, authority, community, hiring…)
3. Who should it reach?
4. 2–5 accounts you watch or compete with.
5. Anything off-limits (topics, claims, words) and who approves posts.

Write the answers into `account.json` (`purpose`, `platforms`, `competitors`) and section 1 of the profile.

## 3. Connect Buffer
```bash
uv run sma buffer channels        # find this account's channels
uv run sma buffer link <slug> --channel <id> [--channel <id> …]
uv run sma sync <slug> --days 365
uv run sma schedule-info <slug>   # existing posting slots = the owner's current cadence
```
If a platform isn't connected in Buffer, note it in section 2 and point the owner to `docs/buffer-setup.md` §3.

### 3b. Deep analytics for the main platform (offer; owner decides)
Buffer's depth is basic for TikTok, YouTube (Shorts only), LinkedIn profiles and Threads, and it has no
follower/audience data. For the account's primary platform offer:
- YouTube → `docs/connect-youtube.md` → `uv run sma connect youtube <slug>` (watch time, retention, traffic, demographics)
- Instagram → `docs/connect-instagram.md` → `uv run sma connect instagram <slug>` (reach, saves, shares, Reels watch time, demographics)
- TikTok → `docs/connect-tiktok.md` → `uv run sma import tiktok <slug> <export>` (watch time, completion)
- Threads → `docs/connect-threads.md` → `uv run sma connect threads <slug>` (views, shares, demographics)
- X → `docs/connect-x.md` → `uv run sma connect x <slug>` (link/profile clicks, bookmarks — paid API, ask first)
- LinkedIn → `docs/connect-linkedin.md` → `uv run sma connect linkedin <slug> --mode member|org` (saves, sends,
  follower demographics — needs LinkedIn approval; set expectations)
Then `uv run sma sync <slug> --days 365` again. Keys always via `uv run sma setup keys --only …`.

## 4. Discover (public data)
For each owned profile URL:
```bash
uv run sma discover <profile-url> --account <slug> --limit 50
```
- Instagram profiles need instaloader (`uv sync --extra instagram`) or the Apify MCP
  (`apify/instagram-profile-scraper`). LinkedIn/X profiles → Apify MCP actors. Set run limits and
  tell the owner the estimated cost before running a paid actor.
- Also fetch the link-in-bio / website (Firecrawl or WebFetch) for positioning language.

## 5. Baseline numbers
```bash
uv run sma report <slug> --days 180 --save
uv run sma report <slug> --days 180 --kpi views --json      # second lens for video-first accounts
uv run sma account-metrics <slug> --metric 'audience:*'     # if a connector provided demographics
```
Copy the baseline (KPI median per channel, posts/week, strongest and weakest buckets with n) into
profile section 7. If < 15 scored posts, say the baseline is thin.

## 6. Watch the work (video accounts)
Run `video-breakdown` on the **top 3 and bottom 3** videos by lift (or by views from discovery):
```bash
uv run sma video <url> --account <slug> --context "<purpose + audience in one line>"
```
Summarize recurring hook types, formats, pacing and what separates winners from losers.

## 7. Infer voice, audience, pillars
Read 20–30 recent captions/posts (`uv run sma posts <slug> --limit 30`, discovery JSON). Use:
- voice → `knowledge/onboarding/voice-analysis-framework.md`, `knowledge/onboarding/voice.md`
- audience → `knowledge/onboarding/audience-template.md`, `knowledge/onboarding/jobs-to-be-done.md`
- positioning → `knowledge/onboarding/positioning.md`
- pillars → cluster posts by topic; share of output + median lift per cluster
Mark all of it 🔎 with the evidence (post ids / URLs).

## 8. Competitors (light pass)
`uv run sma discover <url> --account <slug> --competitor --limit 30` for each; fill section 8 with
what they do that this account doesn't. Deep work belongs to `competitor-scan`.

## 9. Goals & KPIs
Propose **one** primary KPI tied to the purpose (deep-analytics metrics like `averageViewPercentage`,
`retentionHook`, `completionRate`, `saves` are valid once a connector provides them) (see `knowledge/analytics/metrics-by-goal-and-report.md`,
`knowledge/analytics/goals-north-framework.md`) plus ≤2 supporting. Set `primary_kpi` in account.json to a
Buffer metric type (`engagementRate`, `reach`, `views`, `saves`, `shares`, `clicks`, …).

## 10. Confirm with the owner
Show a short summary: purpose, audience, voice (3 adjectives with "but not"), pillars, KPI, baseline,
3 biggest opportunities. Ask them to correct anything. Flip confirmed lines to ✅, put the rest in
section 10 (open questions), set `"status": "active"`, and add the first entries via `log-learning`.

## Done when
- profile.md sections 1–9 filled, each line ✅ or 🔎-with-source
- account.json: platforms, competitors, channels, connectors (if any), primary_kpi, timezone, status=active
- `reports/` has the baseline; `videos/` has the top/bottom breakdowns (if video)
- learnings.md has ≥3 hypotheses to test
