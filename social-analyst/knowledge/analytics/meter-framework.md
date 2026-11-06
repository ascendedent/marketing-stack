<!-- Source: social-media-skills/skills — skills/analytics-and-reporting/references/the-meter-framework.md. Vendored as reference reading for this project; tool names inside (e.g. WoopSocial, other skill names) refer to the source library — in this repo use the `sma` toolkit and the skills in .agents/skills. -->

# The METER framework — measure what maps to goals, then act

Most reporting drowns in vanity metrics and changes nothing. METER turns native platform data into
**decisions**: measure what maps to your goals, read it honestly, and close the loop. WoopSocial
post analytics covers **TikTok, LinkedIn, Facebook, Instagram, Pinterest, YouTube, and Bluesky**; everything else comes from **native dashboards** (the agent
interprets; it never fabricates).

## M — Map metrics to goals
- Start from the **goal** (awareness / engagement / traffic / conversion / loyalty). Each goal → **1
  primary KPI + ~2 supporting**; fix the **measurement window**.
- The filter: **if it won't change next week's action, it's a diagnostic, not a KPI.** Aim for **3–5**.
  (Targets themselves: `goals-and-kpis` / `social-strategy`.)

## E — Extract
- For **TikTok, LinkedIn, Facebook, Instagram, Pinterest, YouTube, and Bluesky**, the first source is **WoopSocial post analytics** (lifetime views, impressions,
  unique impressions, likes, reactions, comments, shares, saves, clicks; LinkedIn Pages engagement
  rate). Snapshots, not a date range, and reading a post does not refresh them.
- **Bluesky** post counts come from WoopSocial — it still has no rich native dashboard. Use UTM links
  and qualitative reads for what WoopSocial doesn't store.
- **X, Threads, and Reddit**, plus watch time, retention, CTR, traffic sources, story exits, follower
  counts, and profile visits, still come from the **native dashboard**.
- Add **GA4 + UTM** for off-platform conversions. Never invent a figure. A missing WoopSocial field is
  a gap, not a zero.

## T — Trim to the signal
- Cut vanity (followers/impressions/likes as headlines). Keep the **signal**: saves, shares, watch
  time/retention/completion, **ER by reach**, follower-growth-rate, CTR, conversions.
- Use the **platform-specific** signal (IG saves · TikTok shares · LinkedIn dwell · YouTube watch time)
  and the **distribution → attention → action** stack.

## E — Evaluate honestly
- **Benchmark relative** to your own trend + vertical/competitors, not platform averages.
- **Correlation ≠ causation**; **small samples and single posts lie** (variance/seasonality) — don't
  overreact. **Attribution undercounts ~30–50%** — read directional signals. Isolate variables via
  `experimentation-and-ab-testing`.

## R — Report & re-cycle
- **Flip the hierarchy:** outcomes first, content metrics explain why. Standardized template, ~30/10 min.
- End with **Recommendations — 3 specific next actions.** **Tier cadence** (weekly pulse / monthly
  trends / quarterly strategy). **Close the loop** → feed `content-recycling`, `experimentation-and-ab-testing`,
  `social-strategy`.

## The analytics brief a request should fill
```
GOAL + KPIs: goal → 1 primary + 2 supporting; measurement window
SOURCE: WoopSocial post analytics for the covered platforms; native dashboards + GA4/UTM otherwise
SIGNAL: the platform-specific signal metric + the funnel stack (not vanity)
EVALUATE: vs own trend + vertical; sample size; causation; attribution caveat
REPORT: outcomes first → why → 3 recommendations; cadence tier
LOOP: which winners to scale / cut / test next
```
