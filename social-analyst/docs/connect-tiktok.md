# Import TikTok Studio exports (optional depth)

TikTok's public APIs don't give owners watch time, completion or traffic data, and Buffer's TikTok
analytics are basic. TikTok Studio's own export is the compliant way to get them.

## Export (owner, ~2 min)
Desktop: https://www.tiktok.com/tiktokstudio → **Analytics**
- **Content** tab → date range (pick the longest offered) → **Export / Download data** →
  CSV or XLSX. This is the per-video file (views, likes, comments, shares, saves, watch time, average
  watch time, watched full video %).
- Optional: **Overview** and **Followers** tabs → export for daily trends.

Mobile: Profile → ☰ → **TikTok Studio** → **Analytics** → export where offered (some regions only allow desktop).

## Import
```bash
uv run sma import tiktok <slug> ~/Downloads/Content.csv
uv run sma import tiktok <slug> ~/Downloads/Overview.xlsx      # daily series → account metrics
uv run sma report <slug> --kpi views
```
- Kind is auto-detected (per-video vs daily); force with `--kind content|overview|followers`.
- Header names vary by Studio version and language; the result lists `mapped` and `unmapped` columns —
  check that views/likes/average watch time mapped.
- Post times in exports have no timezone; they're read in the account's `timezone` (account.json).
- Re-importing the same videos updates them (one metrics snapshot per day), so a weekly export
  builds a growth history. Videos also posted via Buffer merge into the Buffer post when the export
  includes the video link/id.
