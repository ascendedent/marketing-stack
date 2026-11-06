"""Import TikTok Studio exports (CSV or XLSX).

TikTok's official APIs don't expose watch time, retention, traffic sources or follower activity for
owned accounts, so the creator's own export is the compliant route (docs/connect-tiktok.md).
Header names drift between Studio versions/locales: we fuzzy-match and keep unmapped columns in raw.
Ported from aryaminus/socials-assistant (packages/vault/src/importers/tiktok-csv.ts).

Kinds detected:
- content  : one row per video (title, post time, video id/link, views, likes, comments, shares,
             saves, watch time, avg watch time, watched full %, reach…)
- overview : one row per day (date, video views, profile views, likes, comments, shares…)
- followers: one row per day (date, followers / net followers)
- other    : stored as daily account metrics where a date column exists
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from datetime import datetime
from pathlib import Path

from .. import config, store


def _snake(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", h.strip().lower()).strip("_")


def _num(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("%", "")
    if not s or s in ("-", "--"):
        return None
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kKmM]?)", s)
    if m:
        return float(m.group(1)) * {"": 1, "k": 1e3, "m": 1e6}[m.group(2).lower()]
    if re.fullmatch(r"\d+:\d{2}(:\d{2})?", s):  # h:mm:ss or m:ss → seconds
        parts = [int(x) for x in s.split(":")]
        return float(sum(p * 60 ** i for i, p in enumerate(reversed(parts))))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*s", s)
    return float(m.group(1)) if m else None


def _date(v) -> str | None:
    if isinstance(v, datetime):
        return v.isoformat()
    s = str(v or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%m/%d/%Y, %I:%M %p", "%m/%d/%Y %H:%M",
                "%m/%d/%Y", "%d/%m/%Y", "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            pass
    return None


def _rows(path: Path) -> list[dict]:
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        out = []
        for ws in load_workbook(path, read_only=True, data_only=True).worksheets:
            it = ws.iter_rows(values_only=True)
            header = next(it, None)
            if not header:
                continue
            hs = [_snake(str(h or "")) for h in header]
            out += [dict(zip(hs, r)) for r in it if any(c not in (None, "") for c in r)]
        return out
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return [{_snake(k or ""): v for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]


VIDEO_MAP = [  # (canonical metric, predicate on snake header)
    ("views", lambda h: h in ("views", "video_views", "total_views", "total_play", "plays")),
    ("likes", lambda h: h in ("likes", "total_likes", "likes_count")),
    ("comments", lambda h: h in ("comments", "total_comments", "comments_count")),
    ("shares", lambda h: h in ("shares", "total_shares", "shares_count")),
    ("saves", lambda h: h in ("saves", "favorites", "total_saves", "add_to_favorites", "favourites")),
    ("reach", lambda h: h in ("reach", "reached_audience", "total_reach")),
    ("totalTimeWatched", lambda h: "total" in h and "watch" in h and "time" in h),
    ("averageTimeWatched", lambda h: "average" in h and "watch" in h or h in ("avg_watch_time", "average_watch_time")),
    ("completionRate", lambda h: "watched_full" in h or "full_video" in h or "completion" in h),
    ("follows", lambda h: "new_followers" in h or h == "followers_gained"),
]


def _localize(iso: str | None, tz: str) -> str | None:
    """Studio exports are in the creator's local time with no offset: attach the account tz, emit UTC."""
    if not iso:
        return None
    from zoneinfo import ZoneInfo
    d = datetime.fromisoformat(iso)
    if d.tzinfo is None:
        d = d.replace(tzinfo=ZoneInfo(tz))
    return d.astimezone(ZoneInfo("UTC")).isoformat()


def import_file(slug: str, path: str, kind: str | None = None) -> dict:
    p = Path(path).expanduser()
    rows = _rows(p)
    if not rows:
        raise SystemExit("file has no data rows")
    headers = set(rows[0])
    acct = config.load_account(slug)
    handle = next((x.get("handle", "") for x in acct.get("platforms", []) if x.get("service") == "tiktok"), "")
    db = store.connect()

    if kind is None:
        if headers & {"video_id", "video_link", "video_title", "title", "post_time", "video_post_time"}:
            kind = "content"
        elif any("follower" in h for h in headers) and "date" in headers:
            kind = "followers"
        elif "date" in headers:
            kind = "overview"
        else:
            kind = "other"

    if kind == "content":
        channel_id = store.native_channel_id(db, slug, "tiktok", handle or "tiktok", handle or "TikTok")
        mapping = {}
        for h in headers:
            for metric, pred in VIDEO_MAP:
                if metric not in mapping.values() and pred(h):
                    mapping[h] = metric
                    break
        n = 0
        for r in rows:
            link = next((str(r[h]) for h in ("video_link", "link", "url") if r.get(h)), None)
            vid = str(r.get("video_id") or (re.search(r"/video/(\d+)", link or "") or [None, None])[1] or "")
            title = str(r.get("video_title") or r.get("title") or r.get("caption") or "")
            sent = _localize(_date(r.get("post_time") or r.get("video_post_time") or r.get("posted_on") or r.get("date")),
                             acct.get("timezone") or config.env("SMA_TIMEZONE"))
            if not vid:
                vid = hashlib.sha1(f"{title}|{sent}".encode()).hexdigest()[:16]
            metrics = {m: _num(r.get(h)) for h, m in mapping.items()}
            if metrics.get("averageTimeWatched") and "minute" in next(h for h, m in mapping.items() if m == "averageTimeWatched"):
                metrics["averageTimeWatched"] *= 60
            if metrics.get("views"):
                eng = sum(metrics.get(k) or 0 for k in ("likes", "comments", "shares", "saves"))
                metrics["engagementRate"] = 100 * eng / metrics["views"]
            store.upsert_native_post(db, account=slug, service="tiktok", native_id=vid, channel_id=channel_id,
                                     sent_at=sent, text=title, url=link, post_type="video", media_kind="video",
                                     metrics=metrics, raw={k: str(v) for k, v in r.items()})
            n += 1
        db.commit()
        return {"kind": kind, "videos": n, "mapped": mapping, "unmapped": sorted(headers - set(mapping))}

    date_col = "date" if "date" in headers else next((h for h in headers if "date" in h), None)
    if not date_col:
        raise SystemExit(f"can't find a date column in {sorted(headers)}; pass --kind content if this is per-video")
    n = 0
    for r in rows:
        day = _date(r.get(date_col))
        if not day:
            continue
        for h, v in r.items():
            if h == date_col or (val := _num(v)) is None:
                continue
            store.put_account_metric(db, slug, "tiktok", handle, f"daily_{h}", val, day=day[:10], source=f"tiktok_studio:{p.name}")
            n += 1
    db.commit()
    return {"kind": kind, "daily_values": n, "columns": sorted(headers - {date_col})}
