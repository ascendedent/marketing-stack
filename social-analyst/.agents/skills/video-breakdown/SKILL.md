---
name: video-breakdown
description: Download a social video (TikTok, Reels, Shorts, X, YouTube, or a local file) and send it to Gemini for a structured breakdown — hook and first 3 seconds, scene-by-scene with timestamps, transcript, on-screen text, music, pacing, CTA, retention risks, improvements, reusable pattern. Also compares winners vs losers to find what separates them. Use for "break down this video", "why did this reel do well", "analyze our top videos", or reverse-engineering a competitor's viral post.
---

# Video breakdown

## One video
```bash
uv run sma video <url-or-path> --account <slug> --context "<account purpose + audience, one line>" --markdown
```
- Cached by source; `--force` to redo. Saved to `accounts/<slug>/videos/*.{json,md}`.
- Public YouTube: add `--direct` to skip the download (Gemini reads the URL).
- Login-walled / age-gated: set `YTDLP_COOKIES_FROM_BROWSER=firefox` (or chrome) in `.env`.
- Needs `GEMINI_API_KEY`. Model: `GEMINI_VIDEO_MODEL` (default `gemini-3.8-flash`), sampled at
  `GEMINI_VIDEO_FPS` (default 2). Use 3–4 fps for very fast-cut edits.

Present: the hook (first frame, 0–3s, type, strength + why), the 2–3 retention risks with timestamps,
the 3 best improvements, and the replicable pattern. Don't paste the whole scene table unless asked.

## Winners vs losers (the useful version)
1. `uv run sma report <slug> --json` → take `top_posts` and `bottom_posts` with video media
   (or the highest/lowest-view posts from `accounts/<slug>/discovery/*.json`).
2. Break down 3–5 of each (same `--context`).
3. Compare on: hook type & strength, time-to-first-cut, text-on-screen in first frame, face in first
   frame, length, pacing, CTA placement, audio. Make a small table; a difference only counts if it
   holds for most winners and few losers.
4. Write the result as hypotheses with n via `log-learning`; propose an `experiment` for the strongest.

## Competitor / viral reverse-engineering
Same command without `--account` (or with `--account <slug>` to file it under that client).
Use `knowledge/video/deconstruction-framework.md`, `why-things-spread.md`, `replicability.md` to
separate the transferable mechanism from what only worked for that creator.

## Limits & cost
- Files API: up to 2 GB (free) / 20 GB (paid); downloads are capped at 720p, plenty for analysis.
- ~300 tokens per second of video at high resolution — a 60s reel ≈ 20k tokens. Batch thoughtfully.
- Breakdowns describe people by role and appearance, never identify private individuals.
