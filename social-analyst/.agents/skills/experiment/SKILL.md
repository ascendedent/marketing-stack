---
name: experiment
description: Design or read out a content experiment for an owned account — one variable (hook style, posting slot, format, length, CTA), a primary KPI, a minimum sample, and a decision rule — then record the result. Use when a pattern is promising but low-n, when asked "should we test X", or to evaluate a test that's been running.
---

# Experiment

Social data is small and noisy. Tests are how a low-n pattern becomes a learning.

## Design
1. Hypothesis from a report bucket or video comparison: "Question hooks lift engagementRate on LinkedIn".
2. One variable. Everything else (pillar mix, channel, rough slot) held as steady as possible.
3. KPI = the account's primary KPI unless the variable obviously targets another (e.g. hooks → views/reach).
4. Sample: ≥ 6 posts per arm, alternating arms across the same weekdays/slots. Fewer = directional only.
5. Decision rule written *before* data: e.g. "adopt if arm B median lift ≥ 1.2× arm A and ≥ 4 of 6 B posts beat A's median".
6. Make posts traceable: put `[exp:<short-name>:A|B]` at the end of the Idea title, and once each
   goes live add its Buffer post id + arm to the learnings entry (`sma posts <slug>` shows ids). Idea
   titles don't carry over to the published post, so the id list is the source of truth.
7. Log it in `learnings.md` with `Status: hypothesis` and the rule. Reserve slots in `content-plan`.

Recipes and pitfalls: `knowledge/experiments/test-framework.md`, `knowledge/experiments/what-to-test.md`.

## Readout
1. `uv run sma sync <slug>` and wait until the last test post is ≥ 72h old.
2. `uv run sma report <slug> --days <since test start> --json` → `scored_posts` has `lift` for every
   post id; pick the ids listed in the learnings entry.
3. Apply the pre-written rule. Report: arms, n, medians, verdict, and caveats (seasonality, one viral outlier).
4. Update the `learnings.md` entry → `confirmed` or `retired`; if confirmed, update profile §7.
