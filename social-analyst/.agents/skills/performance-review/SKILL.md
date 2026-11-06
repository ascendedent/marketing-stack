---
name: performance-review
description: Analyze an owned account's performance — sync Buffer metrics, run the deterministic pattern report, explain trends and what's working or not (timing, format, media, length, hooks, hashtags), and end with 3 concrete actions. Use for "how are we doing", weekly/monthly reports, "what's working", "best time to post", trend questions, or before planning content.
---

# Performance review

The numbers come from `sma`. Your job is interpretation and decisions, never arithmetic over pasted data.

## Steps
1. Read `accounts/<slug>/profile.md` (purpose, primary KPI) and the tail of `learnings.md`.
2. Refresh and report:
   ```bash
   uv run sma sync <slug> --days 120
   uv run sma report <slug> --days 90 --kpi <primary_kpi> --save      # weekly: --days 28
   uv run sma report <slug> --days 90 --kpi reach --json               # optional second lens
   ```
   `sma sync` also refreshes YouTube/Instagram connectors when connected. TikTok exports are manual —
   if the newest TikTok data is > 7 days old, ask the owner for a fresh Studio export (docs/connect-tiktok.md).
3. Read the report in this order: account level (followers change, audience, traffic) → channels table →
   last-28d vs prior-28d → top/bottom posts →
   breakdowns (weekday, hour band, media, post type, length, question, hashtags).
4. For each candidate pattern, check: n ≥ 5 in the bucket? Consistent across channels? Confounded
   (e.g. all videos were also on Tuesdays)? Drop or flag anything that fails.
5. Explain the top 3 posts and bottom 3: open them (`external_link`) or their text; for videos run
   `video-breakdown`. A pattern without a "why" is just a coincidence report.
6. Compare with `learnings.md`: does this confirm, contradict or extend an existing hypothesis?

## Output (keep under ~400 words; link the saved report for detail)
```
## <Account> — <window>
**Headline:** the one change that matters most (with numbers + n).
**What's working:** 2–3 patterns · lift · n · why we think so
**What isn't:** 1–2 patterns · lift · n · hypothesis
**Watch:** low-n signals worth testing
**Do next:** exactly 3 actions, each tied to a number above (post X more, move slot Y, test Z)
```
Benchmarks when the owner asks "is that good?": `knowledge/analytics/platform-benchmarks.md` —
but always lead with the account's own trend (relative beats absolute).

Then: `log-learning` for anything new; offer `content-plan` to act on it; offer `experiment` for the
top low-n signal.

## Notes
- Buffer analytics depth varies by network (advanced: FB pages, IG business, X, LinkedIn pages;
  basic: LinkedIn profiles, TikTok, YouTube Shorts, Threads, Pinterest; none: Bluesky, Google
  Business). The report's `metrics_seen` column tells you what exists — don't ask for what's not there.
- Follower growth / audience demographics are not in Buffer's API. They come from connectors
  (YouTube, Instagram), TikTok imports, or discovery snapshots — `sma account-metrics <slug>` shows
  each value's `source`; say which you used.
- YouTube packaging (title + thumbnail): `--kpi thumbnailCtr` once Reporting API data has arrived.
- Link-driven accounts with X or LinkedIn connected: `--kpi clicks`.
- Video-first accounts with a connector: also run `--kpi averageViewPercentage` (YouTube) or
  `--kpi completionRate` (IG Reels/TikTok) and compare hooks via `retentionHook` — attention beats likes.
- Frameworks: `knowledge/analytics/meter-framework.md`, `knowledge/analytics/analytics-2026-reality.md`.
