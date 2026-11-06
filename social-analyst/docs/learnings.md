# Learnings — APIs, platforms, tools

Project-wide facts that cost time to learn. Account-specific findings go in `accounts/<slug>/learnings.md`.
Dates are when verified. Append new ones; mark stale ones instead of deleting.

## Buffer API (verified live 2026-11-03 against api.buffer.com)
- New GraphQL API only: `POST https://api.buffer.com`, `Authorization: Bearer <personal key>`. Keys
  from publish.buffer.com/settings/api. Legacy `api.bufferapp.com` rejects them.
- Per-post metrics: `Post.metrics { type value unit }` + `metricsUpdatedAt`. Metric types:
  impressions, reach, views, reactions, likes (FB subcount), comments, shares, reposts, quotes,
  saves, follows, clicks, engagementRate (%), viewers, totalTimeWatched (min), averageTimeWatched (s),
  free/paidSubscriptions, postCount (aggregate only). Old names (retweets, favorites, replies,
  reblogs, repins, link_clicks) are retired.
- Metrics refresh ~daily. A missing metric = network didn't report it, not zero.
- `aggregatedPostMetrics(input: {organizationId, startDateTime, endDateTime (≤365d), channelIds})`.
  Mixed-network aggregates **drop** metrics not shared by every channel instead of zero-filling.
- Metrics need a personal key; OAuth app clients can't get insights.
- No channel-level metrics (followers, demographics) in the schema.
- `posts(first, after, input: {organizationId, filter: {channelIds, status[], postTypes, dueAt:{start,end}, createdAt}, sort})`
  — Relay pagination, forward-only, ≤50 per page. Status: draft, error, needs_approval, scheduled, sending, sent.
- Post type lives in `metadata { ... on <Service>PostMetadata { type } }` — every service's metadata
  has `type` (post, reel, short, story, carousel, thread, …).
- `createPost.assets` is a list of `{image:{url}}` / `{video:{url, metadata:{thumbnailOffset,title}}}` /
  `{document:{…}}`. Modes: addToQueue, customScheduled (needs dueAt), shareNext, shareNow.
- Ideas: `createIdea(input:{organizationId, content:{title,text,services,date,media,tags,aiAssisted}, group:{groupId}})`.
  Ideas reject video. `updateIdea` replaces content wholesale. **Ideas can't be deleted via the API**
  — never create probe ideas. Tags must be existing `{id,name,color}`; orgs have a small tag cap.
- Channel `postingSchedule { day times paused }` + `timezone` give the owner's real slots.
- Rate limits are per account across every key and the MCP: Free 150/15min, 600/day.
  Query complexity cap 175k points, depth 25. 429 → `Retry-After` (client retries).
- Media must be public, direct, stable HTTPS URLs. No upload endpoint.
- Analytics depth by network: advanced (FB pages, IG business, X, LinkedIn pages), basic (LinkedIn
  profiles, Pinterest, TikTok, YouTube Shorts only, Threads, Mastodon, Substack), none (Bluesky,
  Google Business). Reels analytics coverage is inconsistent across Buffer's docs — check
  `metrics_seen` in the report rather than assuming.

## Writing rules that came from real mistakes
- Default every write to an Idea; drafts second; publishing only on an explicit "post it now".
- LinkedIn's 3,000 limit counts UTF-16 units: emoji and unicode-bold count 2; every URL counts 24.
  An over-limit card on the board is not a favor — cut before filing. First comment ≤ 1,250.
- Pull the last ~8 sent posts on a channel before drafting; don't repeat a beat unless the news is new.
- One identity per channel. Shared Buffer logins with several brands make it easy to cross-post a
  voice by accident — the channel must match the account whose voice the copy is in.
- If a board column name you rely on is missing, stop and ask; don't create structure silently.

## Video understanding (Gemini) — verified docs 2026-11-03
- TikTok / Reels / X videos must be downloaded (yt-dlp) and uploaded via the Files API; Gemini can
  only fetch public YouTube URLs directly.
- Files API: 2 GB free / 20 GB paid per file; poll until `ACTIVE` before calling the model.
- Default sampling 1 fps; short social clips need 2–4 fps for the hook. ~300 tokens/s at high
  media resolution (~100 at low).
- Structured output: `response_mime_type="application/json"` + `response_json_schema` from Pydantic.
- Model ids churn (2.5-era ids retire 2026-12-01). Keep the id in `.env` (`GEMINI_VIDEO_MODEL`).
- The google-genai SDK 2.x also has an Interactions API with "agentic" video processing for long
  videos; not needed for short-form.
- **Not yet run end to end in this repo** — no Gemini key was available when the toolkit was built.
  First real run: confirm the model id resolves and the JSON validates, then delete this line.

## First-party connectors (built 2026-11-03; exercised offline against faked responses only — YouTube, Instagram, Threads, X, LinkedIn)
- YouTube: Analytics API per-video reports need `dimensions=video` with `filters=video==id1,id2…`
  (chunk ≤50). Retention = `audienceWatchRatio` by `elapsedVideoTimeRatio`, one video per call.
  OAuth apps left in **Testing** expire refresh tokens after 7 days — publish to production.
  Brand-account channels: pick the channel at the Google account chooser.
- Instagram: Instagram-Login tokens (graph.instagram.com) last 60 days; refresh with
  `refresh_access_token?grant_type=ig_refresh_token` (sync does it after 30 days). Metric names drift
  between Graph versions (impressions/plays → views); request in bulk, fall back one by one.
  Reels duration isn't in the API — ffprobe the `media_url`. Demographics need ≥100 followers.
  business_discovery (competitor stats) works only through the Facebook-Login host.
- TikTok: no owner retention/traffic via API; Studio export is the route. Export times have no
  timezone — read them in the account's tz. Headers drift by version/locale.
- Native posts merge into the Buffer post whose `externalLink` contains the native id, so a video
  published through Buffer is one row with both metric sets.
- Competitor follower counts live under `account = "competitor:<slug>"` so they never blend into the
  client's own trend.
- YouTube Reporting API: `channel_reach_basic_a1` rows are split by country/subscription status etc.;
  sum impressions and impression-weight CTR per video/day. First reports arrive ~24–48h after the job is
  created. Only send the OAuth token to `*.googleapis.com` download URLs.
- X: `non_public_metrics` only for the owner's posts < 30 days old — request them for that window only,
  public metrics for the rest. Every read is billed (pay-per-use since Feb 2026).
- LinkedIn: memberCreatorPostAnalytics is one call per (post, metric); entity param is
  `(share:<urlencoded urn>)` or `(ugc:<urlencoded urn>)`. organizationalEntityShareStatistics omits
  posts with no activity (= zeros) and only covers 12 months. Needs `LinkedIn-Version: YYYYMM` and
  `X-Restli-Protocol-Version: 2.0.0`; versions sunset after ~1 year. Post URNs come from Buffer's
  externalLink. Both scopes require Community Management API approval.
- Threads: skip `REPOST_FACADE` items; user `views` insight is a daily series, others `total_value`.
  Tokens refresh via `refresh_access_token?grant_type=th_refresh_token`.
- **First live run of each connector:** confirm field names against real responses, then delete the
  "offline only" note above.

## Setup flow
- Keys are entered through `sma setup keys` (one-shot form on 127.0.0.1 with a random path nonce),
  written to `.env` with 0600 permissions, validated live, and the result cached by value
  fingerprint (`data/.key_checks.json`) so the offline status shows known-bad keys.
- Claude Code: SessionStart hook runs `scripts/session_start.sh` (stdout lands in context).
  Codex/Grok: AGENTS.md instructs the agent to run it first. The script never fails the session.

## Discovery
- yt-dlp: reliable for YouTube channels (`/videos`, `/shorts`), TikTok profiles, single IG/X posts.
  `instagram:user` (profile listing) is marked broken upstream — use instaloader with a logged-in
  throwaway session, or Apify.
- Apify actors cost per result (~$1.5–2.6 per 1k, varies). Quote cost and cap results before running.
- Public data can't give reach, saves, retention or demographics — only first-party APIs can.

## Agent portability
- AGENTS.md is canonical (Codex, Grok read it; Claude reads CLAUDE.md, which imports it).
- Skills: real files in `.agents/skills` (Codex, Grok); `.claude/skills` symlink for Claude Code.
- MCP: Claude reads `.mcp.json`; Codex needs `.codex/config.toml` (trusted projects only); Grok reads
  `.grok/config.toml` and also `.mcp.json` until you run/dismiss `/import-claude`.
  `scripts/sync_mcp.py` generates the TOML from `.mcp.json`.
- python `mcp` SDK 2.x renamed FastMCP → `mcp.server.mcpserver.MCPServer`.
