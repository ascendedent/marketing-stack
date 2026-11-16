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

## Buffer publishing: drafts, media links, reels (verified live 2026-11-13 to 2026-11-15)
- **Buffer does not copy media in.** A post keeps the URL it was created with; Buffer's screens load it
  in the browser and its workers fetch it at send time. There is no upload mutation in the API. Host the
  file somewhere link-readable and leave it there until the post is sent.
- **The link has to display in a browser, not just download.** A Google Drive download link
  (`drive.usercontent.google.com/download?id=…`) is served as an attachment with
  `cross-origin-resource-policy: same-site`: fine for a video (Buffer makes its own thumbnail), but
  every picture preview in Buffer comes up blank. For a picture use
  `https://lh3.googleusercontent.com/d/<file id>=s0` (file shared by link). `thumbnailUrl` on an image
  asset is ignored, so the main `url` must be the displayable one.
- **Drafts:** `createPost(input:{channelId, text, assets, saveToDraft:true, needsApproval:false,
  mode:customScheduled, schedulingType:automatic, dueAt, tagIds, metadata})` gives status `draft` on
  that date; nothing sends until a person schedules it. Read the post back and assert `status == draft`
  before reporting success. Facebook needs `metadata.facebook.type` (post, reel or story);
  `firstComment` rides in the same object.
- **Editing:** `editPost` rejects a Facebook post without `metadata.facebook.type`, and returns
  "Post must have either text or media" unless the current `text` is resent (posts with no caption need
  `assets` resent instead). Leave out `saveToDraft` and `mode` and a scheduled post stays scheduled at
  its time. Check status, dueAt and text before and after each edit.
- **Sent posts are final through the API:** `deletePost` on a sent post returns
  "Account is not allowed to perform this action on post". Fix those on the network itself.
- **Meta reels are capped at 90 seconds through the API.** A longer video goes up as `type: post`;
  make a separate cut of 90 s or less for `type: reel`. A reel cannot carry a first comment, so do not
  put "sources in the comments" in a reel's voiceover or caption.
- **Tags:** `tagsV2(input:{organizationId})` lists them; match by name, case-insensitive, and pass
  `tagIds`. A missing tag should mean "no tag", not a failed post.
- **Make the uploader idempotent.** Write the post id to a file beside the media and refuse to run
  when it exists; a retry otherwise makes a second draft.
- **Agents run with a temporary home folder.** A tool that relies on a config in `~` (rclone, gcloud)
  fails inside an agent run even though it works in your shell. Pass the config path explicitly.
- **Reading a small page's numbers:** rank nothing under three days old, compare like with like (reels
  with reels), and treat fewer than four comparable posts as "not enough data", which is a valid report.

## Posting straight to Meta (verified live 2026-11-16, Graph API v27.0)
Setup steps are in `post-direct-to-meta.md`; the tool is `scripts/meta_publish.py`.
- **Facebook can only be gated by scheduling.** There is no draft box in the API. A scheduled post
  (`published=false` + `scheduled_publish_time`, 20 minutes to about a month out) waits in Business
  Suite's planner and can be read back (`published` / `is_published` false) and deleted by id.
- **A picture scheduled on `/photos` alone is invisible in Business Suite.** It publishes, and
  `/{page}/scheduled_posts` lists it, but the Scheduled tab does not show it. Upload the picture with
  `published=false&temporary=true`, then make the post on `/{page}/feed` with
  `attached_media[0]={"media_fbid":…}`, `published=false`, `scheduled_publish_time` and
  `unpublished_content_type=SCHEDULED`.
- **Large videos go up in pieces.** One multipart request with a 300 MB file to
  `graph-video.facebook.com/{page}/videos` came back as a non-JSON error. Use `upload_phase=start`
  (with `file_size`), `transfer` (send `video_file_chunk` from `start_offset` to `end_offset`, repeat
  until they are equal), then `finish` with the description and the schedule fields.
- **Reels:** `/{page}/video_reels` `upload_phase=start` → POST the bytes to the returned `upload_url`
  with headers `Authorization: OAuth <page token>`, `offset: 0`, `file_size` → `upload_phase=finish`
  with `video_state=SCHEDULED`. 90 seconds at most.
- **A comment can be attached while the video is still scheduled:** `POST /{video-id}/comments` with
  the page token. This also works where a scheduler tool says a reel cannot carry a first comment.
- **A killed upload can still have created the post.** A reel test that timed out client-side was
  found scheduled afterwards. After any failed or interrupted run, list `/{page}/scheduled_posts` and
  delete strays by id. When cleaning up, delete only ids you created; never loop over everything listed.
- **Instagram refused a direct upload** (`upload_type=resumable` → `ProcessingFailedError` on
  `rupload.facebook.com/ig-api-upload`, with either token). `video_url` pointing at a public link works:
  create the container, poll `status_code` until `FINISHED` (a few minutes), then `media_publish`.
  Containers expire after 24 hours, so prepare close to the posting time.
- **Threads** takes a public `video_url` too, 5 minutes and 500 characters at most. A reply to your own
  post (`reply_to_id`) stands in for a first comment.
- **Text comes back trimmed.** Meta drops trailing whitespace from a caption, so compare stripped text
  when verifying a moved post, and do the "create, verify, then delete the old copy" steps so that a
  failed comparison cannot leave both copies scheduled.
- **Post numbers that still exist:** `post_media_view` (views), `post_total_media_view_unique` (reach),
  `post_clicks`, `post_video_views`, `post_video_avg_time_watched` and `post_video_view_time` (both
  milliseconds). `post_impressions`, `post_impressions_unique` and `post_engaged_users` are gone. Ask
  for one metric per call: one that does not apply to the post fails the whole request. Reactions,
  comments and shares come from the post's own fields (`reactions.summary(total_count).limit(0)` etc.).
- **Every call hung for 20 seconds on one machine:** a dead IPv6 route to `graph.facebook.com`. Force
  IPv4 (`httpx.HTTPTransport(local_address="0.0.0.0")`, or `urllib3.util.connection.HAS_IPV6 = False`
  for requests) before blaming the API.
- **Moving scheduled posts off a scheduler:** for each one, create the Meta post with the scheduler's
  current text and time, read it back as unpublished, and only then delete it from the scheduler. Leave
  anything due within the hour where it is.

## YouTube: direct API versus Buffer (2026-11-16)
- **Direct upload works but is locked to private.** A Google Cloud project made after mid-2020 has every
  API upload forced to private until Google's "YouTube API Services audit" form is approved, which is
  separate from OAuth app verification and can take weeks. Service accounts and API keys cannot upload;
  it needs an OAuth client (Desktop app) and a one-time browser sign-in.
- **The sign-in picks one channel.** Read back `channels?mine=true` and check the title before building
  on it; the first attempt here landed on a different channel of the same person.
- **An External app left in "Testing" expires its login every 7 days**, and only listed test users can
  sign in. Publishing to production needs a home page, privacy policy and an authorized domain filled
  in, but not Google's verification, for an app only its owner uses.
- **Through Buffer it is a few fields.** `metadata.youtube` takes `title` (100 characters), `categoryId`,
  `privacy` (`public`, `unlisted`, `private`), `madeForKids`, `notifySubscribers`, `embeddable`,
  `license`, `isAiGenerated`. The post `text` is the description (5000 characters, no `<` or `>`).
  YouTube has no first comment in Buffer: put sources at the end of the description.
- **A vertical video of 3 minutes or less is a Short**, whatever it is called. For a channel that wants
  Shorts, send the full video when it is 3 minutes or less and the shorter cut only when it is longer.

