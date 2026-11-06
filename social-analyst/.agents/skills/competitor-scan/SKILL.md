---
name: competitor-scan
description: Benchmark an account against competitors or peer accounts using public data — posting cadence, formats, top content, view/engagement medians, hooks — and find whitespace the account can own. Use for "how do we compare", "what are competitors doing", "who's winning in our niche", or finding content gaps.
---

# Competitor scan

1. Targets: `account.json → competitors` (add any the owner names). 3–6 is enough.
2. Pull each (free first):
   ```bash
   uv run sma discover <profile-url> --account <slug> --competitor --limit 40
   ```
   Instagram → instaloader extra or Apify `apify/instagram-scraper`; LinkedIn/X → Apify MCP actors.
   Quote the cost before running paid actors and cap results.
3. Compare on what public data supports: posts/week, format mix, median views (and likes/comments
   where shown), engagement per view, caption length, hashtag use, top 5 posts. Use the same window
   for everyone. Follower-normalize when comparing accounts of different size.
4. Break down each competitor's top 2 videos (`video-breakdown`) — look for mechanisms, not topics.
5. Whitespace: topics/formats competitors win with that the account doesn't do, and topics the
   account owns that nobody else covers. Use `knowledge/competitors/scout-framework.md` and
   `whitespace-recipes.md`.

## Output
Table (account · posts/wk · format mix · median views · top hook types) → 3 things to borrow (with
the mechanism, not the copy) → 2 whitespace bets → 1 thing to stop. Update profile §8 and log
hypotheses via `log-learning`.

Public data only. No scraping behind logins of accounts you don't own; no DMs; no identifying
private individuals in comments.
