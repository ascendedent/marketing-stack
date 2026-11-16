# Connect YouTube Analytics (optional depth)

Buffer gives basic YouTube numbers (Shorts only). This adds watch time, average view duration and
percentage, retention points (first 3 seconds, 25/50/75%, end), subscribers gained per video, the
channel's daily trend, traffic sources and viewer demographics. Read-only scopes. ~10 minutes, once.

## 1. Google Cloud project
1. Open https://console.cloud.google.com/ signed in as the Google account that owns (or manages) the channel.
2. Top bar → project picker → **New project** → name it e.g. "social-analyst" → Create → select it.

## 2. Enable two APIs
**APIs & Services → Library**, search and **Enable** both:
- **YouTube Data API v3**
- **YouTube Analytics API**

## 3. OAuth consent screen
**APIs & Services → OAuth consent screen** (or "Google Auth Platform → Branding/Audience"):
- User type **External** → app name "Social Analyst", your email as support + developer contact → Save.
- **Audience / Test users**: add the Google account that owns the channel.
- Scopes: you can skip adding them here; the app requests `youtube.readonly` and `yt-analytics.readonly` at sign-in.

## 4. Avoid the 7-day expiry
While the app's publishing status is **Testing**, Google expires refresh tokens after 7 days and the
daily sync will start failing. For personal use: **Audience → Publish app → In production**. You'll
see an "unverified app" warning at sign-in — that's expected for your own app; click
*Advanced → Go to Social Analyst (unsafe)*. No verification is needed for your own channels.

## 5. Create the OAuth client
**APIs & Services → Credentials → Create credentials → OAuth client ID** → Application type
**Desktop app** → Create. Copy the **Client ID** and **Client secret**, then in the project:
```bash
uv run sma setup keys --only GOOGLE_OAUTH_CLIENT_ID,GOOGLE_OAUTH_CLIENT_SECRET
```
(Alternatively download the JSON and set `YOUTUBE_CLIENT_SECRET_FILE=/path/to/client_secret.json` in `.env`.)

## 6. Connect and sync
```bash
uv run sma connect youtube <slug>     # browser opens → choose the channel's account → Allow
uv run sma sync <slug>                # pulls videos + analytics into the store
uv run sma report <slug> --kpi averageViewPercentage
```
Brand accounts: at the Google chooser pick the **channel** (brand account), not just your personal profile.
Tokens are stored in `data/tokens/youtube__<slug>.json` (owner-only permissions, gitignored).

## What you get
Per video (in `post_metrics`): views, likes, comments, shares, totalTimeWatched (min),
averageTimeWatched (s), averageViewPercentage, follows (subs gained), durationSeconds, engagementRate,
and for the top 15 by views: retentionHook (≈ at 3s), retention25/50/75, retentionEnd (% of viewers).
After the reporting job has produced reports: impressions, thumbnailCtr.
Account level (`sma account-metrics <slug>`): followers, daily views/watch minutes/subs gained/lost,
`traffic:<source>`, `audience:age_gender:*`, `audience:country:*`.

**Thumbnail impressions and CTR** come from the YouTube Reporting API (`channel_reach_basic_a1`). The
first `sync` creates the reporting job; Google produces the first daily reports ~24–48 hours later
(with roughly a month of backfill), and every later sync ingests the new ones. They appear per video as
`impressions` and `thumbnailCtr` (%) — use `sma report <slug> --kpi thumbnailCtr` to compare packaging.

## Publishing the app, when Google will not let you
**Publish app** can refuse until the Branding page has a home page, a privacy policy link and an
authorized domain. For an app only you use, Google does not review them; they only have to exist.
Put a short, honest privacy page and terms page on a domain you own (what the tool reads, that nothing
is sold or shared, how to revoke access, links to the YouTube Terms of Service and Google Privacy
Policy), mark them `noindex`, enter the two links, add the domain under **Authorized domains**, then
publish. Until then only listed test users can sign in ("Access blocked … has not completed the Google
verification process" means the account is not a test user and the app is still in Testing).

The app's owner and the channel's owner can be different Google accounts. An **Internal** app only
admits accounts in your Workspace, so use **External** when the channel belongs to a personal account.

After sign-in, check which channel you got (`channels?mine=true`): Google signs in to one channel at a
time, and it is easy to land on another channel of the same person.

## Uploading through the API (think twice)
Uploading needs the extra scope `youtube.upload` (and `youtube.force-ssl` to comment) on the same OAuth
client, requested at sign-in. Two limits decide whether it is worth it:
- Every upload from a project created after mid-2020 is **forced to private** until Google approves the
  "YouTube API Services – Audit and Quota Extension Form" (project number, what the tool does, the API
  calls used, privacy and terms links, a screen recording). That can take weeks. Without it the tool can
  only upload private videos for a person to publish in YouTube Studio.
- The default daily quota allows only a handful of uploads.

If drafts in a scheduler are enough, connect the YouTube channel in Buffer instead: it needs no Google
Cloud project, and `learnings.md` lists the `metadata.youtube` fields a post takes.

