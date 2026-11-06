# Connect Threads insights (optional depth)

Buffer's Threads analytics are basic. This adds per-post views, likes, replies, reposts, quotes and
shares; daily account views; clicks; follower count over time; and follower demographics (≥100 followers).

## 1. Meta app with the Threads use case (~10 min)
1. https://developers.facebook.com/apps → **Create app** → use case **Access the Threads API** → name it.
2. **Use cases → Access the Threads API → Customize → Permissions**: add `threads_basic` and
   `threads_manage_insights`.
3. **App roles → Roles → Add people → Threads Tester** → the Threads account to analyze. Accept the
   invite in Threads: Settings → Account → Website permissions → Invites.
4. **Use cases → Threads API → Settings → User token generator** → **Generate access token** for that
   tester → copy the token (long-lived, 60 days).

## 2. Connect
```bash
uv run sma setup keys --only THREADS_ACCESS_TOKEN
uv run sma connect threads <slug>
uv run sma sync <slug>
```
Several Threads accounts: store each as `THREADS_ACCESS_TOKEN_<NAME>` and pass `--token-env`.

The token is copied to `data/tokens/threads__<slug>.json` and refreshed by `sync` after 30 days, so it
never hits the 60-day expiry while the daily sync runs. The app can stay in development mode — it
only reads accounts added as testers. Posts made through Buffer merge into the Buffer post (matched by
the post's shortcode in the permalink). Version: `THREADS_API_VERSION` (default `v1.0`).
