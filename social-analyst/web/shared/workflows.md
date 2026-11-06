# Workflows — Social Analyst (web edition)

## 1. Onboarding (new account)
Goal: a filled-in `account-profile-template.md`, each line marked ✅ (owner confirmed) or 🔎 (your inference + evidence).

1. **Intake.** Ask everything at once, and only what you can't find yourself:
   1. Profile links for each platform, and which is primary.
   2. In one sentence, what is the account for (sales, leads, authority, community, hiring…)?
   3. Who should it reach?
   4. 2–5 accounts they watch or compete with.
   5. Off-limits topics or claims, and who approves posts.
2. **Connect.** If the Buffer connector is available, list channels and confirm which belong to this account. If not, ask for exports (§2 data list). Also browse the public profile pages and the website/link-in-bio for positioning language if you can.
3. **Baseline.** Pull ~180 days of sent posts (connector) or the exports. Run `report.py --days 180`. Note the KPI median per channel, posts/week, and the strongest and weakest buckets with n. Under ~15 scored posts, say the baseline is thin.
4. **Videos.** For a video account, have the owner run the Gemini prompt (§3) on the top 3 and bottom 3 videos and paste the results back. Look for what separates them.
5. **Voice, audience, pillars.** Read 20–30 recent posts. Voice: 3–5 adjectives, each with a "but not", plus signature moves and banned patterns. Audience: role, pains, desires, what they believe. Pillars: cluster posts by topic, with each cluster's share of output and median lift.
6. **Competitors.** Look at public pages only: their posting rhythm, formats, and what gets traction that this account doesn't do.
7. **KPI.** Propose one primary KPI tied to the purpose (see frameworks-metrics.md) plus at most 2 supporting ones.
8. **Confirm.** Summarize: purpose, audience, voice, pillars, KPI, baseline, and the 3 biggest opportunities. Ask for corrections. Output the completed profile as one markdown block and ask the owner to save it to the Project files.

## 2. Performance review
1. Data: connector (sent posts with analytics for the window) or fresh exports.
   - **Buffer**: Analyze/Analytics → choose channel → date range → Export (CSV).
   - **LinkedIn Page**: Page admin → Analytics → Posts → Export.
   - **Instagram/Facebook**: Meta Business Suite → Insights → Content → Export.
   - **TikTok**: TikTok Studio (desktop) → Analytics → Content → Export.
   - **YouTube**: Studio → Analytics → Advanced mode → Content → Export (CSV).
   - **X**: analytics.x.com → Posts → Export.
2. `python report.py <files> --kpi <primary KPI> --days 28` for a weekly review, or `--days 90` for a monthly one. Video accounts: run again with `--kpi views` (or watch-time metrics if present).
3. Interpret per the instructions (n, ⚠, confounds, the why behind top and bottom posts).
4. Output: headline → working → not working → watch → 3 actions. Offer a content plan (§4) and a test for the best low-n signal (§6).

## 3. Video breakdown
These web apps can't reliably watch video, so the owner uses Gemini:
1. Give them `video-breakdown-prompt.md`, filled with the account context (purpose and audience, one line).
2. They open gemini.google.com, upload the video (or paste a public YouTube link), paste the prompt, and send you the result.
3. You interpret it: hook strength, retention risks, the 3 best improvements, and the reusable pattern. For winners vs losers, compare 3–5 of each on hook type, time to first cut, text on the first frame, face on the first frame, length, pacing, CTA placement and audio. A difference only counts if most winners have it and few losers do.
If your app does accept a video upload, you can try it directly, but say if you could only see some frames.

## 4. Content plan
1. Read the profile (voice, pillars, cadence, guardrails), the latest learnings, and the last ~10 posts.
2. Count: the agreed cadence, else the current posts/week. Allocate slots to pillars, tilted toward higher-lift pillars. Use the slots and times that win in the report. Reserve about 20% for experiments.
3. Show a plan table (slot, channel, pillar, format, angle, evidence) and get a nod.
4. Write each post. Hooks per frameworks-hooks.md. Self-score per frameworks-post-scorer.md and rewrite weak ones. Respect limits. For a video post, write the script and shot list.
5. File them (§5) or hand over copy-ready blocks.

## 5. Buffer drafts (connector)
- Default: create an **Idea** on the Create board, with a title that names account · slot · angle. Second choice: a **draft** post (saveToDraft) with the intended time.
- Only queue or schedule with the owner's OK for that post. Never shareNow without "post it now".
- Don't create test Ideas: they can't be deleted through the API.
- Media must be public, direct HTTPS URLs (no Drive or Dropbox share links). Ideas don't accept video.
- Afterwards, list what you filed: title, channel, slot.

## 6. Experiment
1. Hypothesis from a report bucket or video comparison, with exactly one variable.
2. KPI: the primary one, unless the variable targets something else (hooks → views or reach).
3. At least 6 posts per arm, alternating arms across the same days and slots.
4. Write the decision rule before any data comes in. Example: adopt B if its median lift is ≥ 1.2× A's and at least 4 of its 6 posts beat A's median.
5. Log it in Learnings with the post links as they go live. For the readout, export again and run `report.py --json`, then apply the rule.
