---
name: log-learning
description: Record a finding about an account — a pattern, a video insight, an experiment result, an owner preference — in accounts/<slug>/learnings.md (and profile.md when confirmed) so the next session, on any model, starts from it. Use after a performance review, video comparison, experiment readout, or when the owner corrects you or states a preference.
---

# Log a learning

Append to `accounts/<slug>/learnings.md` (newest at the bottom, never rewrite history; change status
on an existing entry instead of duplicating it):

```
## YYYY-MM-DD — <one-line claim>
- Evidence: <report date + bucket + lift + n | video keys | experiment readout | "owner said">
- Confidence: low | medium | high
- Action: <what we do differently because of this>
- Status: hypothesis | confirmed | retired
```

Rules:
- Absolute dates only. Numbers only from `sma` output, with n.
- Owner preferences/corrections are `confirmed` immediately and also go into `profile.md` (§5 voice
  or §9 guardrails) — they outrank data.
- When an entry is `confirmed`, reflect it in `profile.md §7`. When `retired`, remove it from §7.
- Project-wide (not account-specific) facts about APIs, tools or platforms go in `docs/learnings.md`.
