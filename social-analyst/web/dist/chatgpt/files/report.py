#!/usr/bin/env python3
"""Social Analyst — portable pattern report (web edition).

Runs in any chat app's code tool (Claude analysis/code execution, ChatGPT code interpreter, Grok code
execution) or locally. Standard library only; reads .xlsx too if openpyxl happens to be installed.

Input: one or more files —
  * JSON from the Buffer connector (a list of posts, or {"posts": [...]}, or {"edges": [{"node": …}]}),
    each post with text, sentAt/dueAt, channel or channelService, externalLink, assets, and
    metrics: [{type, value}] (Buffer format) or a flat dict of numbers;
  * CSV/XLSX exports (Buffer, LinkedIn, Meta Business Suite, TikTok Studio, YouTube Studio, X…) —
    headers are fuzzy-matched (date, text/caption/title, channel/platform, link, media type, and
    metric columns like impressions, reach, views, likes, comments, shares, saves, clicks, engagement rate).

Usage:  python report.py posts.json [more.csv …] [--kpi engagementRate] [--days 90] [--tz UTC] [--json]

Method (same as the local `sma report`): medians not means; each post scored as KPI ÷ its channel's
median ("lift", 1.0 = typical) so different channels compare fairly; missing metrics are never treated
as zero; every bucket shows n and flags n < 5; posts younger than 48h are excluded (still accruing).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

ENGAGEMENT_PARTS = ["reactions", "likes", "comments", "shares", "reposts", "saves", "quotes"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
HASHTAG = re.compile(r"(?<!\w)#(\w{2,})", re.UNICODE)

# canonical metric ← header synonyms (lowercase, non-alphanumerics collapsed to "_")
METRIC_SYNONYMS = {
    "impressions": ["impressions", "impression_count", "total_impressions", "views_impressions"],
    "reach": ["reach", "unique_impressions", "accounts_reached", "members_reached", "reached_audience"],
    "views": ["views", "video_views", "plays", "total_views", "total_play", "view_count"],
    "reactions": ["reactions", "reaction_count"],
    "likes": ["likes", "like_count", "total_likes", "hearts"],
    "comments": ["comments", "comment_count", "replies", "reply_count", "total_comments"],
    "shares": ["shares", "share_count", "total_shares", "sends"],
    "reposts": ["reposts", "retweets", "retweet_count", "reshares"],
    "saves": ["saves", "saved", "bookmarks", "bookmark_count", "favorites", "add_to_favorites"],
    "clicks": ["clicks", "link_clicks", "url_link_clicks", "click_count", "outbound_clicks"],
    "follows": ["follows", "new_followers", "followers_gained", "subscribers_gained", "subscribers"],
    "engagementRate": ["engagement_rate", "engagement_rate_pct", "er", "engagement"],
    "averageTimeWatched": ["average_watch_time", "avg_watch_time", "average_view_duration"],
    "averageViewPercentage": ["average_percentage_viewed", "average_view_percentage", "avg_view_pct"],
    "completionRate": ["watched_full_video", "completion_rate", "watched_full_video_pct"],
}
FIELD_SYNONYMS = {
    "date": ["sent_at", "sentat", "date", "post_time", "published", "published_at", "publish_time", "created",
             "created_at", "posted", "posted_on", "time", "video_post_time", "date_published", "duedat", "due_at"],
    "text": ["text", "caption", "post", "content", "message", "title", "video_title", "description", "post_text", "copy"],
    "channel": ["channel", "account", "profile", "page", "channel_name", "network", "platform", "service"],
    "link": ["link", "url", "permalink", "post_link", "external_link", "externallink", "video_link"],
    "media": ["media", "media_type", "type", "format", "post_type", "content_type"],
    "id": ["id", "post_id", "video_id", "tweet_id", "media_id"],
}

FUZZY_FIELDS = {"date": ["date", "time", "published", "posted", "created"],
                "text": ["title", "caption", "text", "content", "message", "description"],
                "link": ["link", "url"], "channel": ["channel", "account", "page", "profile"]}


def snake(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("%", "")
    if s in ("", "-", "--", "n/a", "N/A"):
        return None
    m = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*([kKmM]?)", s)
    if m:
        return float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()]
    if re.fullmatch(r"\d+:\d{2}(:\d{2})?", s):
        parts = [int(x) for x in s.split(":")]
        return float(sum(p * 60 ** i for i, p in enumerate(reversed(parts))))
    return None


def parse_date(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        d = v
    else:
        s = str(v).strip()
        d = None
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%m/%d/%Y %H:%M", "%m/%d/%Y, %I:%M %p",
                        "%m/%d/%Y %I:%M %p", "%m/%d/%Y", "%d/%m/%Y %H:%M", "%b %d, %Y", "%B %d, %Y", "%d %b %Y"):
                try:
                    d = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    pass
        if d is None:
            if re.fullmatch(r"\d{10}(\.\d+)?", s):
                d = datetime.fromtimestamp(float(s), timezone.utc)
            else:
                return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def pick(row: dict, names: list[str]):
    for n in names:
        if n in row and row[n] not in (None, ""):
            return row[n]
    return None


def from_buffer_post(p: dict) -> dict:
    ms = p.get("metrics")
    if isinstance(ms, list):
        metrics = {m.get("type") or m.get("name"): num(m.get("value")) for m in ms}
    elif isinstance(ms, dict):
        metrics = {k: num(v) for k, v in ms.items()}
    else:
        metrics = {}
    ch = p.get("channel") or {}
    assets = p.get("assets") or []
    kinds = sorted({a.get("type") for a in assets if isinstance(a, dict) and a.get("type")})
    meta = p.get("metadata") or {}
    return {
        "id": p.get("id"), "text": p.get("text") or "", "sent": parse_date(p.get("sentAt") or p.get("sent_at") or p.get("dueAt")),
        "channel": (ch.get("name") if isinstance(ch, dict) else ch) or p.get("channelId") or p.get("channel_name") or "?",
        "service": p.get("channelService") or (ch.get("service") if isinstance(ch, dict) else None) or p.get("service") or "",
        "link": p.get("externalLink") or p.get("link"), "media": "+".join(kinds) if kinds else (p.get("media") or "text"),
        "post_type": (meta.get("type") if isinstance(meta, dict) else None) or p.get("post_type") or "post",
        "metrics": {k: v for k, v in metrics.items() if k and v is not None},
    }


def from_row(raw: dict, source: str) -> dict:
    row = {snake(k): v for k, v in raw.items() if k is not None}
    metrics = {}
    used = set()
    for canon, syns in METRIC_SYNONYMS.items():
        for s in syns:
            if s in row and (v := num(row[s])) is not None:
                metrics[canon] = v
                used.add(s)
                break
    pct_sign = any("%" in str(row.get(x, "")) for x in METRIC_SYNONYMS["engagementRate"])
    fields = {k: pick(row, v) for k, v in FIELD_SYNONYMS.items()}
    for k, words in FUZZY_FIELDS.items():  # e.g. "created_date", "post_publish_time", "post_title"
        if fields[k] in (None, ""):
            col = next((c for c in row if any(w in c for w in words) and row[c] not in (None, "")
                        and (k != "date" or parse_date(row[c]))), None)
            if col:
                fields[k] = row[col]
                used.add(col)
    for s in sum(FIELD_SYNONYMS.values(), []):
        used.add(s)
    for k, v in row.items():  # keep other numeric columns as extra metrics
        if k not in used and (n := num(v)) is not None and not k.endswith("_id"):
            metrics.setdefault(k, n)
    media = str(fields["media"] or "text").lower()
    return {"id": str(fields["id"] or ""), "text": str(fields["text"] or ""), "sent": parse_date(fields["date"]),
            "channel": str(fields["channel"] or Path(source).stem), "service": "", "link": fields["link"],
            "media": "video" if any(w in media for w in ("video", "reel", "short")) else
                     "carousel" if any(w in media for w in ("carousel", "album", "document")) else
                     "image" if any(w in media for w in ("image", "photo", "picture")) else
                     "text" if media in ("text", "", "status", "post") else media,
            "post_type": media, "metrics": metrics, "_er_pct_sign": pct_sign}


def percentify(rows: list[dict]) -> list[dict]:
    """Some exports give engagement rate as a fraction (0.034), others as percent (3.4). Decide per file."""
    ers = [r["metrics"]["engagementRate"] for r in rows if "engagementRate" in r["metrics"]]
    if any(r.get("_er_pct_sign") for r in rows):
        return rows
    if ers and max(ers) <= 1 and any(e > 0 for e in ers):
        NOTES.append("Engagement rate looked like a fraction (all values ≤ 1) in a CSV/XLSX export and was "
                     "converted to percent. If your export already uses percent, ignore engagementRate here.")
        for r in rows:
            if "engagementRate" in r["metrics"]:
                r["metrics"]["engagementRate"] *= 100
    return rows


NOTES: list[str] = []


def load(path: str) -> list[dict]:
    rows = _load(path)
    return rows if Path(path).suffix.lower() == ".json" else percentify(rows)


def _load(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("posts") or data.get("data") or data.get("edges") or data.get("items") or [data]
        out = []
        for item in data:
            node = item.get("node", item) if isinstance(item, dict) else None
            if isinstance(node, dict):
                out.append(from_buffer_post(node) if ("metrics" in node or "sentAt" in node) else from_row(node, path))
        return out
    if p.suffix.lower() in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
        except ImportError:
            sys.exit("This is an .xlsx file and openpyxl isn't available — save it as CSV and retry.")
        rows = []
        for ws in load_workbook(p, read_only=True, data_only=True).worksheets:
            it = ws.iter_rows(values_only=True)
            header = None
            for r in it:  # some exports have a title row before the header
                if r and sum(c not in (None, "") for c in r) >= 3:
                    header = [str(c or "") for c in r]
                    break
            if header:
                rows += [from_row(dict(zip(header, r)), path) for r in it if any(c not in (None, "") for c in r)]
        return rows
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    # skip title/preamble rows: the header is the first row with ≥3 non-empty cells
    start = next((i for i, cells in enumerate(csv.reader(lines)) if sum(bool(c.strip()) for c in cells) >= 3), 0)
    return [from_row(r, path) for r in csv.DictReader(lines[start:])]


def kpi_value(m: dict, kpi: str):
    if kpi == "engagementRate":
        if "engagementRate" in m:
            return m["engagementRate"]
        denom = m.get("reach") or m.get("impressions") or m.get("views")
        if not denom:
            return None
        parts = [m[k] for k in ENGAGEMENT_PARTS if k in m and not (k == "likes" and "reactions" in m)]
        return 100 * sum(parts) / denom if parts else None
    if kpi == "engagements":
        parts = [m[k] for k in ENGAGEMENT_PARTS if k in m and not (k == "likes" and "reactions" in m)]
        return sum(parts) if parts else None
    return m.get(kpi)


def summ(vals):
    return {"n": len(vals), "median_lift": round(statistics.median(vals), 2) if vals else None, "low_n": len(vals) < 5}


def band(h):
    return f"{h // 3 * 3:02d}-{h // 3 * 3 + 3:02d}h"


def length_bucket(n):
    for edge, label in [(80, "<80"), (200, "80-199"), (500, "200-499"), (1000, "500-999"), (1500, "1000-1499")]:
        if n < edge:
            return label
    return "1500+"


def report(posts: list[dict], kpi="engagementRate", days=90, tz="UTC", min_age_hours=48) -> dict:
    zone = ZoneInfo(tz) if ZoneInfo else timezone.utc
    now = datetime.now(timezone.utc)
    dated = [p for p in posts if p["sent"]]
    if days and dated:
        newest = max(p["sent"] for p in dated)
        anchor = min(now, newest + timedelta(hours=min_age_hours + 1))  # exports can be old: anchor to the data
        since, fresh = anchor - timedelta(days=days), now - timedelta(hours=min_age_hours)
        dated = [p for p in dated if since <= p["sent"] <= fresh]
    for p in dated:
        p["kpi"] = kpi_value(p["metrics"], kpi)
        p["local"] = p["sent"].astimezone(zone)
    by_ch = defaultdict(list)
    for p in dated:
        by_ch[p["channel"]].append(p)
    channels = []
    for ch, ps in by_ch.items():
        vals = [p["kpi"] for p in ps if p["kpi"] is not None]
        med = statistics.median(vals) if vals else None
        for p in ps:
            p["lift"] = p["kpi"] / med if (med and p["kpi"] is not None) else None
        channels.append({"channel": ch, "posts": len(ps), "with_kpi": len(vals),
                         "kpi_median": round(med, 3) if med is not None else None,
                         "metrics_seen": sorted({k for p in ps for k in p["metrics"]})})
    scored = [p for p in dated if p.get("lift") is not None]

    def bd(fn):
        b = defaultdict(list)
        for p in scored:
            b[str(fn(p))].append(p["lift"])
        return {k: summ(v) for k, v in sorted(b.items(), key=lambda kv: -statistics.median(kv[1]))}

    tags = defaultdict(list)
    for p in scored:
        for h in {t.lower() for t in HASHTAG.findall(p["text"])}:
            tags[h].append(p["lift"])
    ranked = sorted(scored, key=lambda p: -p["lift"])

    def brief(p):
        return {"lift": round(p["lift"], 2), "kpi": round(p["kpi"], 3), "sent": p["local"].strftime("%Y-%m-%d %H:%M"),
                "channel": p["channel"], "media": p["media"], "chars": len(p["text"]), "link": p["link"],
                "text": p["text"][:160].replace("\n", " ")}
    weekly = defaultdict(list)
    for p in scored:
        weekly[(p["local"] - timedelta(days=p["local"].weekday())).date().isoformat()].append(p["lift"])
    return {
        "notes": list(NOTES), "kpi": kpi, "window_days": days, "timezone": tz, "posts_loaded": len(posts), "posts_in_window": len(dated),
        "posts_scored": len(scored), "channels": channels,
        "by_weekday": bd(lambda p: WEEKDAYS[p["local"].weekday()]), "by_hour_band": bd(lambda p: band(p["local"].hour)),
        "by_media": bd(lambda p: p["media"]), "by_post_type": bd(lambda p: p["post_type"]),
        "by_text_length": bd(lambda p: length_bucket(len(p["text"]))), "by_asks_question": bd(lambda p: "?" in p["text"]),
        "by_has_link": bd(lambda p: bool(re.search(r"https?://", p["text"]))),
        "by_hashtag_count": bd(lambda p: min(len(set(HASHTAG.findall(p["text"]))), 5)),
        "hashtags": {h: summ(v) for h, v in sorted(tags.items(), key=lambda kv: -statistics.median(kv[1])) if len(v) >= 3},
        "top_posts": [brief(p) for p in ranked[:5]], "bottom_posts": [brief(p) for p in ranked[-5:][::-1]] if len(ranked) > 5 else [],
        "weekly_trend": [{"week_of": w, "posts": len(v), "median_lift": round(statistics.median(v), 2)} for w, v in sorted(weekly.items())],
    }


def markdown(r: dict) -> str:
    out = [f"# Pattern report — KPI `{r['kpi']}`, last {r['window_days']} days ({r['timezone']})",
           f"{r['posts_scored']} posts scored of {r['posts_in_window']} in window ({r['posts_loaded']} loaded). "
           "lift = post KPI ÷ its channel's median (1.0 = typical). ⚠ = fewer than 5 posts: anecdote, not pattern.", "",
           *[f"> Note: {n}" for n in r.get("notes", [])], "",
           "## Channels", "| channel | posts | with KPI | KPI median | metrics available |", "|---|---|---|---|---|"]
    out += [f"| {c['channel']} | {c['posts']} | {c['with_kpi']} | {c['kpi_median']} | {', '.join(c['metrics_seen'])} |" for c in r["channels"]]
    for title, key in [("Weekday", "by_weekday"), ("Time of day", "by_hour_band"), ("Media", "by_media"),
                       ("Post type", "by_post_type"), ("Text length (chars)", "by_text_length"),
                       ("Asks a question", "by_asks_question"), ("Has link", "by_has_link"),
                       ("Hashtag count", "by_hashtag_count"), ("Hashtags used 3+ times", "hashtags")]:
        if r[key] and len(r[key]) > 1:
            out += ["", f"## {title}", "| bucket | n | median lift |", "|---|---|---|"]
            out += [f"| {k} | {v['n']}{' ⚠' if v['low_n'] else ''} | {v['median_lift']} |" for k, v in r[key].items()]
    for title, key in [("Top posts", "top_posts"), ("Bottom posts", "bottom_posts")]:
        if r[key]:
            out += ["", f"## {title}"] + [f"- **{p['lift']}×** {p['sent']} · {p['channel']} · {p['media']} · {p['chars']}ch — "
                                          f"{p['text']}{' ' + p['link'] if p['link'] else ''}" for p in r[key]]
    if r["weekly_trend"]:
        out += ["", "## Weekly trend (median lift)", " · ".join(f"{w['week_of']}: {w['median_lift']} (n={w['posts']})" for w in r["weekly_trend"][-10:])]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--kpi", default="engagementRate")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--tz", default="UTC")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    posts = [p for f in a.files for p in load(f)]
    if not posts:
        sys.exit("No posts found in the input. Check the file is an export of posts (one row per post).")
    r = report(posts, a.kpi, a.days, a.tz)
    if r["posts_scored"] == 0:
        kpis = sorted({k for p in posts for k in p["metrics"]})
        print(f"No post had the KPI '{a.kpi}'. Metrics available: {kpis}. Re-run with --kpi <one of those>.")
        return
    print(json.dumps(r, indent=2, default=str) if a.json else markdown(r))


if __name__ == "__main__":
    main()
