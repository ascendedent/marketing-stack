# Tutorial: set up Buffer and connect it to the analyst

About 20–30 minutes for a first account. At the end, agents can read every connected channel's posts
and per-post metrics, and can put Ideas and drafts into Buffer for you to approve.

> Why Buffer: one login covers ~14 networks for publishing, the GraphQL API exposes per-post
> metrics, and there's an official MCP server that works in Claude, ChatGPT/Codex and Grok.
> Alternatives are listed at the end if you outgrow it.

---

## 1. Create the Buffer account

1. Sign up at **buffer.com** (email or Google). One Buffer login = one "organization".
   - Managing accounts for **different clients/brands**? Either put them all in one login, or use a
     separate Buffer login per client. The toolkit supports any number of logins (step 5).
2. Pick a plan:
   | plan | channels | analytics | API rate limit |
   |---|---|---|---|
   | Free | 3 | basic, some metrics paywalled | 150 req / 15 min, 600 / day |
   | Essentials | per-channel pricing | full post analytics | 450 / 15 min |
   | Team | per-channel pricing | + approvals, more users | 1,500 / 15 min |
   Start on Free to test; move to **Essentials** once you rely on metrics (some metrics are paid-only).

## 2. Prepare each social account *before* connecting it

Most connection failures are account-type problems on the platform side.

| platform | what it must be | notes |
|---|---|---|
| **Instagram** | **Business or Creator** account, linked to a **Facebook Page** you admin | Personal IG accounts get no analytics and limited publishing. Switch in IG → Settings → Account type. |
| **Facebook** | A **Page** (not a personal profile) where you're admin | Groups aren't supported for analytics. |
| **TikTok** | Business or personal account; you log in to TikTok during connect | Analytics are basic (views/likes/comments/shares). |
| **YouTube** | A channel you own/manage | Analytics in Buffer cover **Shorts** only. |
| **LinkedIn** | Your **profile** and/or **Pages** you're a Super/Content admin of | Pages get advanced analytics; profiles basic. |
| **X (Twitter)** | Any account | Advanced analytics. |
| **Threads** | Account linked to the Instagram login | Basic analytics. |
| **Pinterest** | **Business** account | Basic analytics. |
| **Bluesky / Mastodon / Google Business / Substack** | Any | Bluesky & Google Business: **no analytics** in Buffer. |

## 3. Connect channels

1. In Buffer: **Channels → Connect channel** (or publish.buffer.com → *+ New channel*).
2. Pick the network, log in **as the account that owns/admins it**, approve every permission
   (declining "insights"/"analytics" scopes silently removes metrics later).
3. For Instagram, choose **automatic publishing** when offered (needs the Business/Creator + Page link).
4. Repeat per channel. Check each shows no "Reconnect" warning.

## 4. Set the posting schedule

For each channel: **Settings → Posting schedule** → add time slots (in the channel's time zone).
The analyst reads these slots (`sma schedule-info`) and plans posts into them, and it reads the
channel time zone to bucket weekday/hour patterns correctly.

Optional but useful: on the **Create** board, make sure there's a column named **In Progress** —
agents file their Ideas there by default (`sma idea --column "<name>"` to use another).

## 5. Create the API key and put it in `.env`

1. Go to **publish.buffer.com/settings/api** (Settings → API) and create a **personal API key**.
   - Personal keys are required for metrics (OAuth *app* clients can't read insights).
   - The key is for the **new GraphQL API** (`https://api.buffer.com`). The old REST API
     (`api.bufferapp.com`) will reject it — ignore old tutorials that use it.
2. In this project folder:
   ```bash
   cp .env.example .env
   # edit .env:
   BUFFER_API_KEY=...                 # the main login
   # more logins (other clients/brands), any name you like:
   BUFFER_API_KEY_CLIENTA=...
   # or point at a key file instead of pasting the key:
   BUFFER_API_KEY_CLIENTB_FILE=~/.secrets/buffer-clientb
   ```
   `.env` is gitignored. Never paste the key into chats, issues, or docs.

## 6. Verify

```bash
uv sync                                   # first time only
uv run sma doctor --live                  # → "buffer[default]": "N channels"
uv run sma buffer channels                # ids, service, type, name, timezone per channel
```
Problems:
- `Unauthorized` / `invalid token` → key copied wrong, or it's a legacy REST token. Make a new one in step 5.
- Channel missing → it's in a different Buffer login (add that key) or it needs reconnecting.
- `metrics` empty on old posts → network doesn't report them, the channel was connected after the
  post went out, or the plan paywalls that metric. Missing ≠ zero.

## 7. Create the account in the analyst and link channels

```bash
uv run sma account new acme --name "Acme Co"
uv run sma buffer link acme --channel <channelId> --channel <channelId>
uv run sma sync acme --days 365           # first pull: posts + per-post metrics
uv run sma report acme --days 180         # first look
```
Then ask your agent to run the **onboard-account** skill — it does the rest (discovery, video
breakdowns, voice/audience inference, KPI proposal) and writes `accounts/acme/profile.md`.

Keep metrics fresh: run `uv run sma sync` daily (cron/systemd timer, or a scheduled agent). Each run
stores a dated snapshot, so growth curves build up over time.

## 8. Connect the Buffer MCP to your agent (optional, for interactive use)

`sma` already covers analysis and safe writes. The official Buffer MCP adds interactive browsing
(posts, ideas, templates) inside chat clients. Endpoint: `https://mcp.buffer.com/mcp`.

| client | how |
|---|---|
| **Claude Code** | Already in `.mcp.json` (uses `BUFFER_API_KEY` as a Bearer header). Or OAuth: `claude mcp add --transport http buffer https://mcp.buffer.com/mcp`, then `/mcp` to sign in. |
| **Claude.ai / Desktop** | Settings → Connectors → add custom connector → `https://mcp.buffer.com/mcp` → sign in. |
| **Codex CLI** | `python scripts/sync_mcp.py` writes `.codex/config.toml` (bearer from env), or `codex mcp add buffer --url https://mcp.buffer.com/mcp` for OAuth. Trust the project folder. |
| **ChatGPT** | Settings → Apps & Connectors → developer mode → add MCP server URL. |
| **Grok** | grok.com → Plugins → Buffer (OAuth). Grok CLI: `python scripts/sync_mcp.py` writes `.grok/config.toml`; check with `grok inspect`. |

Tools you'll see: `get_account`, `list_channels`, `list_posts` (with analytics), `get_post`,
`create_post`, `edit_post`, `delete_post`, `get_aggregated_post_metrics`, `list_ideas`,
`create_idea`, `list_idea_groups`, template tools. **Keep tool-approval prompts on** — `create_post`
can publish immediately. The rate limit is shared with your API key.

## 9. Media for posts

Buffer has no upload endpoint: images/videos are passed as **public HTTPS URLs** that must stay
reachable until the post publishes. Drive/Dropbox share links and expiring signed URLs fail.
Use a public bucket (Cloudflare R2 public bucket, S3 + CloudFront, Cloudinary). Ideas accept
images but not video.

## 10. When you need more than Buffer gives you

Buffer has per-post metrics but **no account-level metrics** (followers over time, demographics,
profile views) and only basic depth on some networks. Options, cheapest first:
- **Discovery snapshots** (built in): `sma discover <profile-url> --account <slug>` stores follower
  counts per day for public profiles.
- **Metricool MCP** (free plan works with its MCP): account + audience metrics across most networks.
- **First-party APIs** for depth on your main platform: YouTube Analytics (retention, CTR, traffic
  sources), Instagram Graph API (reach, saves, shares, demographics). Starting code to port is in
  `reference/` (see `docs/sources.md`).
- **Self-hosted**: Postiz (open source) replaces Buffer for publishing + basic analytics.
