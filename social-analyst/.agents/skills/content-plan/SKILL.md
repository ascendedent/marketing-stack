---
name: content-plan
description: Turn analysis into next week's content — pick slots from the account's real posting schedule, choose pillars and formats backed by the performance report and learnings, write the posts in the account's voice, and file them as Buffer Ideas for the owner to approve. Use for "plan next week", "write posts based on what's working", "fill the queue", or after a performance review.
---

# Content plan → Buffer Ideas

## Inputs (read, don't guess)
- `accounts/<slug>/profile.md` — voice, pillars, guardrails, approval rule
- `accounts/<slug>/learnings.md` — confirmed patterns beat hunches; running experiments get their slots
- latest `accounts/<slug>/reports/*-performance.md` (run `performance-review` first if > 7 days old)
- `uv run sma schedule-info <slug>` — the owner's real slots and daily limits
- `uv run sma posts <slug> --status sent --limit 10` and `--status scheduled` — don't repeat recent beats

## Plan
1. Count: use the account's agreed cadence (profile §9). If none, match current posts/week from the report.
2. Allocate slots to pillars by their share target, tilted toward pillars with higher median lift.
3. For each post pick: pillar · format (text/image/carousel/video) · hook type · length band — each
   choice traceable to a report bucket or learning (cite it in the plan, not in the post).
4. Reserve ~20% for experiments (see `experiment`) so the account keeps learning.

Show the plan as a table (slot, channel, pillar, format, angle, evidence) and get a nod before writing
if the owner is present; otherwise proceed.

## Write
- Voice from profile §5; check against "never say". Hooks: `knowledge/writing/hook-generator.md`.
  Self-score with `knowledge/writing/post-scorer.md` and rewrite anything weak.
- Respect platform limits (enforced by `sma`): LinkedIn 3,000 (URLs count 24, emoji 2), X 280,
  Threads 500, Bluesky 300, IG/TikTok captions 2,200. Aim for the length band that wins in the report.
- Video posts: write the script/shot list in the Idea text; the owner produces the video.

## File (default: Ideas, not posts)
```bash
uv run sma idea <slug> --channel <service[:type]> --title "<Account> · <slot> · <angle>" \
  --date <slot ISO UTC> --text-file /path/to/post.txt            # --dry-run first if unsure
```
Follow `buffer-publishing` for everything else (draft posts, media, never publish).

## Report back
Table of what was filed (title, channel, slot) + the one-line evidence per post. Note which slots carry experiments.
