# Connect Instagram insights (optional depth)

Adds reach, saves, shares, total interactions, Reels average watch time and completion rate,
follower count over time, profile views and follower demographics. Needs an Instagram
**Business or Creator** account (Settings → Account type and tools → Switch to professional).

Two routes. Pick **A** unless you need competitor lookups.

| | A. Instagram Login (default) | B. Facebook Login |
|---|---|---|
| needs a Facebook Page | no | yes, linked to the IG account |
| token life | 60 days, auto-refreshed by sync | page token (long-lived) |
| competitor stats (`sma ig-lookup`) | no | yes (business_discovery) |

## A. Instagram API with Instagram Login (~10 min)

1. https://developers.facebook.com/apps → **Create app** → use case **Other** → type **Business** → name it.
2. In the app: **Add product → Instagram** → **API setup with Instagram login**.
3. **Generate access tokens → Add account** → log in as the Instagram account → allow
   `instagram_business_basic` and `instagram_business_manage_insights`.
   (If it's not offered: **App roles → Roles → Add people → Instagram Tester**, then accept the invite
   in Instagram → Settings → Website permissions → Apps and websites → Tester invites.)
4. Copy the generated token (long-lived, 60 days). In the project:
   ```bash
   uv run sma setup keys --only INSTAGRAM_ACCESS_TOKEN
   uv run sma connect instagram <slug>
   uv run sma sync <slug>
   ```
   Several IG accounts? Store each under its own name, e.g. `INSTAGRAM_ACCESS_TOKEN_ACME`, and
   `uv run sma connect instagram acme --token-env INSTAGRAM_ACCESS_TOKEN_ACME`.

The token is copied into `data/tokens/instagram__<slug>.json` and refreshed automatically by `sync`
once it's older than 30 days, so it never reaches the 60-day expiry as long as sync runs.
The app can stay in development mode: it only reads accounts you've added yourself.

## B. Instagram API with Facebook Login

1. Same app, add product **Facebook Login for Business**; make sure the IG account is linked to a Page you admin.
2. Graph API Explorer (developers.facebook.com/tools/explorer) → your app → **Get User Access Token** with
   `instagram_basic`, `instagram_manage_insights`, `pages_show_list`, `pages_read_engagement`,
   `business_management` → Generate → exchange for a long-lived token (Access Token Debugger → Extend).
3. ```bash
   uv run sma setup keys --only INSTAGRAM_ACCESS_TOKEN
   uv run sma connect instagram <slug> --host facebook
   uv run sma ig-lookup <slug> <competitor_username>     # public stats of another business account
   ```

## Notes
- Graph version defaults to `v24.0`; set `INSTAGRAM_GRAPH_VERSION` in `.env` to change. Metric names
  shift between versions — `sync` drops unknown metrics one by one and reports them as warnings.
- Demographics need ≥100 followers. Stories are skipped (insights expire after 24h).
- Reels completion rate = average watch time ÷ duration; duration is measured with `ffprobe` on the
  media URL (the API doesn't return it).
