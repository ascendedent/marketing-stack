# Connect X (optional depth, paid API)

Buffer already has advanced X analytics. This adds what only the owner can see: **link clicks and
profile clicks** per post (X keeps these for 30 days), bookmarks and quotes, and follower count over time.

**Cost:** the X API is pay-per-use — every post read is billed (check current pricing at
https://developer.x.com). `sma sync` reads at most 200 posts per run (`max_posts`) and reports
`billed_reads_estimate`. For most accounts, Buffer's X analytics are enough; connect this only if
clicks matter (link-driven accounts) or you need bookmarks.

## 1. Developer app (~10 min)
1. https://developer.x.com → sign in as the account owner → **Developer Portal** → set up billing/credits.
2. **Projects & Apps → Create App** (inside a project).
3. App → **User authentication settings → Set up**:
   - App permissions: **Read**
   - Type of App: **Native App** (public client — no secret needed) or **Web App** (confidential, has a secret)
   - Callback URI: `http://localhost:8765/callback` (exactly; change the port with `SMA_OAUTH_PORT`)
   - Website: any URL you own
4. **Keys and tokens → OAuth 2.0 Client ID and Client Secret** → copy them.

## 2. Connect
```bash
uv run sma setup keys --only X_CLIENT_ID,X_CLIENT_SECRET     # secret may stay blank for Native App
uv run sma connect x <slug>      # browser opens → Authorize app
uv run sma sync <slug>
```
Token is stored in `data/tokens/x__<slug>.json` and refreshed automatically (`offline.access`).

## What you get
Per post: impressions (private count when available), reactions (likes), comments (replies), reposts,
quotes, saves (bookmarks), clicks (URL link clicks), profileClicks, engagementRate. Posts made through
Buffer merge into the Buffer post. Account: followers, following, post_count per day.
Private metrics exist only for posts < 30 days old — older posts get public counts only.
