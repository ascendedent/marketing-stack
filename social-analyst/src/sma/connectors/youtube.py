"""YouTube Data API v3 + YouTube Analytics API v2 for an owned channel (OAuth, read-only scopes).

Adds what Buffer can't: watch time, average view duration/percentage, retention curve points
(hook retention, 25/50/75%), subscribers gained per video, channel daily trend, traffic sources,
and viewer demographics. Setup: docs/connect-youtube.md.

Ported from conorbronsdon/yt-analytics-mcp and aryaminus/socials-assistant (see docs/sources.md).
Thumbnail impressions + CTR come from the YouTube Reporting API (report type channel_reach_basic_a1):
the first sync creates the reporting job; Google starts producing daily reports ~24-48h later and
backfills about 30 days. Each sync ingests new reports and rolls them up per video.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from .. import config, store

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]
DATA_API = "https://www.googleapis.com/youtube/v3"
ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"


def _client_config() -> dict:
    path = config.env("YOUTUBE_CLIENT_SECRET_FILE")
    if path:
        return json.loads(Path(os.path.expanduser(path)).read_text())
    cid, secret = config.secret("GOOGLE_OAUTH_CLIENT_ID"), config.secret("GOOGLE_OAUTH_CLIENT_SECRET")
    if not (cid and secret):
        raise SystemExit("No Google OAuth client. Follow docs/connect-youtube.md, then set YOUTUBE_CLIENT_SECRET_FILE "
                         "or GOOGLE_OAUTH_CLIENT_ID + GOOGLE_OAUTH_CLIENT_SECRET (`uv run sma setup keys`).")
    return {"installed": {"client_id": cid, "client_secret": secret,
                          "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                          "token_uri": "https://oauth2.googleapis.com/token", "redirect_uris": ["http://localhost"]}}


def _token_path(slug: str) -> Path:
    return config.TOKENS / f"youtube__{slug}.json"


def _credentials(slug: str):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    p = _token_path(slug)
    if not p.exists():
        raise SystemExit(f"YouTube not connected for {slug}: `uv run sma connect youtube {slug}`")
    creds = Credentials.from_authorized_user_file(str(p), SCOPES)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except Exception as e:
            raise SystemExit(f"YouTube token refresh failed ({e}). If the OAuth app is in 'Testing', refresh tokens "
                             f"expire after 7 days — publish it (docs/connect-youtube.md §4) and reconnect.") from None
        config.write_private(p, creds.to_json())
    return creds


def connect(slug: str, port: int = 0) -> dict:
    """Interactive browser consent. Prints the URL too, for headless shells."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    acct = config.load_account(slug)
    flow = InstalledAppFlow.from_client_config(_client_config(), SCOPES)
    print("Opening Google consent in your browser. If it doesn't open, use the URL printed below.", flush=True)
    creds = flow.run_local_server(port=port, open_browser=True, prompt="consent", access_type="offline",
                                  authorization_prompt_message="Authorize here: {url}", success_message=
                                  "Connected. You can close this tab and return to your agent.")
    config.TOKENS.mkdir(parents=True, exist_ok=True)
    config.write_private(_token_path(slug), creds.to_json())
    ch = _get(creds, f"{DATA_API}/channels", part="snippet,statistics", mine="true")["items"][0]
    acct.setdefault("connectors", {})["youtube"] = {
        "channel_id": ch["id"], "title": ch["snippet"]["title"], "handle": ch["snippet"].get("customUrl"),
        "token": str(_token_path(slug).relative_to(config.ROOT)), "connected_at": store.now()}
    config.save_account(slug, acct)
    return acct["connectors"]["youtube"]


def _get(creds, url: str, **params) -> dict:
    r = httpx.get(url, params=params, headers={"authorization": f"Bearer {creds.token}"}, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"YouTube API {r.status_code}: {r.text[:400]}")
    return r.json()


def _report(creds, start: str, end: str, metrics: str, **params) -> list[dict]:
    d = _get(creds, ANALYTICS_API, ids="channel==MINE", startDate=start, endDate=end, metrics=metrics, **params)
    cols = [h["name"] for h in d.get("columnHeaders", [])]
    return [dict(zip(cols, row)) for row in d.get("rows") or []]


def _iso_seconds(dur: str | None) -> int | None:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


REPORTING_API = "https://youtubereporting.googleapis.com/v1"
REACH_REPORT = "channel_reach_basic_a1"


def sync_reach(slug: str, creds, db) -> dict:
    """Ingest new channel_reach_basic_a1 reports → native_daily → impressions/thumbnailCtr per video."""
    import csv
    import io
    from urllib.parse import urlparse
    acct = config.load_account(slug)
    yt = acct["connectors"]["youtube"]
    job = yt.get("reach_job_id")
    if not job:
        jobs = _get(creds, f"{REPORTING_API}/jobs").get("jobs", [])
        found = next((j for j in jobs if j.get("reportTypeId") == REACH_REPORT), None)
        if not found:
            r = httpx.post(f"{REPORTING_API}/jobs", json={"reportTypeId": REACH_REPORT, "name": "social-analyst-reach"},
                           headers={"authorization": f"Bearer {creds.token}"}, timeout=60)
            if r.status_code >= 400:
                raise RuntimeError(f"Reporting job create {r.status_code}: {r.text[:300]}")
            found = r.json()
        job = yt["reach_job_id"] = found["id"]
        yt["reach_job_created"] = store.now()
        config.save_account(slug, acct)
    params = {"createdAfter": yt["reach_last_report"]} if yt.get("reach_last_report") else {}
    reports, page = [], None
    while True:
        d = _get(creds, f"{REPORTING_API}/jobs/{job}/reports", **params, **({"pageToken": page} if page else {}))
        reports += d.get("reports", [])
        page = d.get("nextPageToken")
        if not page:
            break
    latest = yt.get("reach_last_report")
    ingested, skipped = 0, 0
    agg: dict[tuple[str, str], list[float]] = {}
    for rep in sorted(reports, key=lambda r: r.get("createTime", "")):
        url = rep.get("downloadUrl")
        host = urlparse(url or "").hostname or ""
        if not url or not (host == "googleapis.com" or host.endswith(".googleapis.com")):
            skipped += 1
            continue  # never send the token anywhere but Google
        r = httpx.get(url, headers={"authorization": f"Bearer {creds.token}"}, timeout=120, follow_redirects=False)
        if r.status_code >= 400:
            skipped += 1
            continue
        ingested += 1
        for row in csv.DictReader(io.StringIO(r.text)):
            day, vid = row.get("date", ""), row.get("video_id")
            if not vid or not day:
                continue
            impr = float(row.get("video_thumbnail_impressions") or 0)
            ctr = float(row.get("video_thumbnail_impressions_ctr") or 0)
            a = agg.setdefault((vid, f"{day[:4]}-{day[4:6]}-{day[6:8]}"), [0.0, 0.0])
            a[0] += impr          # rows are split by country/subscribed status/etc. — sum them
            a[1] += impr * ctr    # clicks, so CTR stays impression-weighted
        latest = max(latest or "", rep.get("createTime", ""))
    for (vid, day), (impr, clicks) in agg.items():
        pid = (db.execute("SELECT id FROM posts WHERE account=? AND service='youtube' AND (id=? OR instr(coalesce(external_link,''), ?) > 0)",
                          (slug, f"youtube:{vid}", vid)).fetchone() or {"id": f"youtube:{vid}"})["id"]
        db.execute("INSERT OR REPLACE INTO native_daily VALUES (?,?,?,?)", (pid, day, "thumbnailImpressions", impr))
        db.execute("INSERT OR REPLACE INTO native_daily VALUES (?,?,?,?)", (pid, day, "thumbnailClicks", clicks))
    # roll up lifetime totals onto the posts we know
    for r in db.execute("""SELECT post_id, sum(CASE WHEN metric='thumbnailImpressions' THEN value END) AS i,
                                  sum(CASE WHEN metric='thumbnailClicks' THEN value END) AS c
                           FROM native_daily WHERE post_id IN (SELECT id FROM posts WHERE account=? AND service='youtube')
                           GROUP BY post_id""", (slug,)).fetchall():
        if r["i"]:
            db.execute("INSERT OR REPLACE INTO post_metrics VALUES (?,?,?,?,?)", (r["post_id"], store.today(), "impressions", r["i"], "count"))
            db.execute("INSERT OR REPLACE INTO post_metrics VALUES (?,?,?,?,?)", (r["post_id"], store.today(), "thumbnailCtr", 100 * r["c"] / r["i"], "percentage"))
    if latest:
        acct = config.load_account(slug)
        acct["connectors"]["youtube"]["reach_last_report"] = latest
        config.save_account(slug, acct)
    return {"reports_ingested": ingested, "reports_skipped": skipped, "video_days": len(agg),
            **({"note": "reporting job is new; Google produces the first reports in ~24-48h"} if not reports and not yt.get("reach_last_report") else {})}


def sync(slug: str, days: int = 365, max_videos: int = 200, retention_top: int = 15) -> dict:
    conn = (config.load_account(slug).get("connectors") or {}).get("youtube")
    if not conn:
        raise SystemExit(f"YouTube not connected for {slug}: `uv run sma connect youtube {slug}`")
    creds = _credentials(slug)
    db = store.connect()
    warnings: list[str] = []
    today = date.today().isoformat()
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)

    ch = _get(creds, f"{DATA_API}/channels", part="snippet,statistics,contentDetails", mine="true")["items"][0]
    handle = ch["snippet"].get("customUrl") or ch["id"]
    st = ch["statistics"]
    for k, m in (("subscriberCount", "followers"), ("viewCount", "lifetime_views"), ("videoCount", "post_count")):
        if st.get(k) is not None:
            store.put_account_metric(db, slug, "youtube", handle, m, st[k])
    channel_id = store.native_channel_id(db, slug, "youtube", ch["id"], ch["snippet"]["title"])

    # uploads in window
    ids, page = [], None
    while len(ids) < max_videos:
        d = _get(creds, f"{DATA_API}/playlistItems", part="contentDetails", maxResults=50,
                 playlistId=ch["contentDetails"]["relatedPlaylists"]["uploads"], **({"pageToken": page} if page else {}))
        for it in d.get("items", []):
            pub = it["contentDetails"].get("videoPublishedAt")
            if pub and datetime.fromisoformat(pub.replace("Z", "+00:00")) >= since_dt:
                ids.append(it["contentDetails"]["videoId"])
        page = d.get("nextPageToken")
        if not page or (d.get("items") and (p := d["items"][-1]["contentDetails"].get("videoPublishedAt"))
                        and datetime.fromisoformat(p.replace("Z", "+00:00")) < since_dt):
            break
    ids = ids[:max_videos]

    videos: dict[str, dict] = {}
    for i in range(0, len(ids), 50):
        for v in _get(creds, f"{DATA_API}/videos", part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50])).get("items", []):
            videos[v["id"]] = v

    analytics: dict[str, dict] = {}
    if videos:
        earliest = min(v["snippet"]["publishedAt"][:10] for v in videos.values())
        for i in range(0, len(ids), 50):
            try:
                for row in _report(creds, earliest, today,
                                   "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares,subscribersGained",
                                   dimensions="video", filters="video==" + ",".join(ids[i:i + 50]), maxResults=50, sort="-views"):
                    analytics[row["video"]] = row
            except RuntimeError as e:
                warnings.append(f"per-video analytics: {e}")

    # retention for the most-viewed videos (one call each)
    retention: dict[str, dict] = {}
    for vid in sorted(videos, key=lambda x: -int(videos[x]["statistics"].get("viewCount", 0)))[:retention_top]:
        try:
            pts = _report(creds, videos[vid]["snippet"]["publishedAt"][:10], today, "audienceWatchRatio",
                          dimensions="elapsedVideoTimeRatio", filters=f"video=={vid}")
        except RuntimeError as e:
            warnings.append(f"retention {vid}: {e}")
            continue
        if not pts:
            continue
        dur = _iso_seconds(videos[vid]["contentDetails"].get("duration")) or 0
        hook_ratio = min(1.0, 3 / dur) if dur else 0.05

        def at(r):
            return min(pts, key=lambda p: abs(p["elapsedVideoTimeRatio"] - r))["audienceWatchRatio"] * 100
        retention[vid] = {"retentionHook": at(hook_ratio), "retention25": at(0.25), "retention50": at(0.5),
                          "retention75": at(0.75), "retentionEnd": at(1.0)}

    for vid, v in videos.items():
        s, a = v["statistics"], analytics.get(vid, {})
        dur = _iso_seconds(v["contentDetails"].get("duration"))
        metrics = {
            "views": a.get("views", s.get("viewCount")), "likes": a.get("likes", s.get("likeCount")),
            "comments": a.get("comments", s.get("commentCount")), "shares": a.get("shares"),
            "totalTimeWatched": a.get("estimatedMinutesWatched"), "averageTimeWatched": a.get("averageViewDuration"),
            "averageViewPercentage": a.get("averageViewPercentage"), "follows": a.get("subscribersGained"),
            "durationSeconds": dur, **retention.get(vid, {}),
        }
        views = float(metrics["views"] or 0)
        if views:
            eng = sum(float(metrics[k] or 0) for k in ("likes", "comments", "shares"))
            metrics["engagementRate"] = 100 * eng / views
        store.upsert_native_post(
            db, account=slug, service="youtube", native_id=vid, channel_id=channel_id,
            sent_at=v["snippet"]["publishedAt"], text=f"{v['snippet']['title']}\n\n{v['snippet'].get('description', '')}",
            url=f"https://www.youtube.com/watch?v={vid}", post_type="short" if dur and dur <= 180 else "video",
            media_kind="video", metrics=metrics, raw={"title": v["snippet"]["title"], "tags": v["snippet"].get("tags")})

    # channel-level: daily trend, traffic sources, demographics
    start = (date.today() - timedelta(days=min(days, 90))).isoformat()
    for name, fn in [
        ("daily", lambda: [store.put_account_metric(db, slug, "youtube", handle, k, r[k], day=r["day"])
                           for r in _report(creds, start, today, "views,estimatedMinutesWatched,subscribersGained,subscribersLost", dimensions="day")
                           for k in ("views", "estimatedMinutesWatched", "subscribersGained", "subscribersLost")]),
        ("traffic", lambda: [store.put_account_metric(db, slug, "youtube", handle, f"traffic:{r['insightTrafficSourceType']}", r["views"])
                             for r in _report(creds, start, today, "views", dimensions="insightTrafficSourceType")]),
        ("age_gender", lambda: [store.put_account_metric(db, slug, "youtube", handle, f"audience:age_gender:{r['ageGroup']}_{r['gender']}", r["viewerPercentage"])
                                for r in _report(creds, start, today, "viewerPercentage", dimensions="ageGroup,gender")]),
        ("country", lambda: [store.put_account_metric(db, slug, "youtube", handle, f"audience:country:{r['country']}", r["views"])
                             for r in _report(creds, start, today, "views", dimensions="country", sort="-views", maxResults=15)]),
    ]:
        try:
            fn()
        except RuntimeError as e:
            warnings.append(f"{name}: {e}")
    db.commit()
    try:
        reach = sync_reach(slug, creds, db)
    except RuntimeError as e:
        reach = {"error": str(e)[:200]}
    db.commit()
    return {"videos": len(videos), "with_analytics": len(analytics), "with_retention": len(retention),
            "reach": reach, "warnings": warnings}
