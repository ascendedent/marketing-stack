"""Public-profile discovery for onboarding (and competitor scans). Cheapest-first:

- yt-dlp (free): YouTube channels/Shorts tabs, TikTok profiles, single IG reels / X posts.
  NOTE: yt-dlp's `instagram:user` profile listing is marked broken upstream; for IG profiles use
  instaloader (`uv sync --extra instagram`) or the Apify MCP.
- instaloader (optional): Instagram profile meta + post history. Use a throwaway login session
  (`instaloader --login <user>`); IG rate-limits anonymous use quickly.
- Anything else (LinkedIn, X profiles at scale): Apify MCP actors or Firecrawl — see AGENTS.md.

Output: accounts/<slug>/discovery/<service>__<handle>.json and rows in public_posts / account_metrics.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import config, store


def detect_service(url: str) -> str:
    host = re.sub(r"^https?://(www\.|m\.)?", "", url).split("/")[0]
    for k, s in {"youtube.com": "youtube", "youtu.be": "youtube", "tiktok.com": "tiktok", "instagram.com": "instagram",
                 "x.com": "twitter", "twitter.com": "twitter", "linkedin.com": "linkedin", "threads.net": "threads",
                 "threads.com": "threads", "facebook.com": "facebook", "pinterest.": "pinterest", "bsky.app": "bluesky"}.items():
        if k in host:
            return s
    return "web"


def _ts(entry: dict) -> str | None:
    if entry.get("timestamp"):
        return datetime.fromtimestamp(entry["timestamp"], timezone.utc).isoformat()
    if d := entry.get("upload_date"):
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return None


def _ydl(opts: dict):
    import yt_dlp
    return yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "ignoreerrors": True, **opts})


def ytdlp_profile(url: str, limit: int = 30, detail: bool = True) -> dict:
    """List a profile's recent posts; with detail=True fetch full metadata (counts) for each."""
    svc = detect_service(url)
    if svc == "youtube" and not re.search(r"/(videos|shorts|streams)/?$", url):
        url = url.rstrip("/") + "/videos"
    with _ydl({"extract_flat": "in_playlist", "playlistend": limit}) as y:
        info = y.extract_info(url, download=False) or {}
    entries = [e for e in (info.get("entries") or []) if e][:limit]
    posts = []
    for e in entries:
        full = e
        if detail and (e.get("url") or e.get("webpage_url")):
            with _ydl({}) as y:
                full = y.extract_info(e.get("webpage_url") or e["url"], download=False) or e
        posts.append({
            "id": full.get("id"), "url": full.get("webpage_url") or full.get("url"),
            "title": full.get("title"), "description": full.get("description"),
            "published_at": _ts(full), "duration": full.get("duration"),
            "views": full.get("view_count"), "likes": full.get("like_count"),
            "comments": full.get("comment_count"), "shares": full.get("repost_count"),
            "tags": full.get("tags"), "track": full.get("track"), "artist": full.get("artist"),
        })
    return {
        "service": svc, "source": "yt-dlp", "url": url,
        "handle": info.get("uploader_id") or info.get("channel_id") or info.get("id"),
        "name": info.get("channel") or info.get("uploader") or info.get("title"),
        "bio": info.get("description"),
        "followers": info.get("channel_follower_count"),
        "posts": posts,
    }


def instaloader_profile(handle: str, limit: int = 30, session_user: str | None = None) -> dict:
    try:
        import instaloader
    except ImportError:
        raise SystemExit("instaloader not installed: `uv sync --extra instagram` (or use the Apify MCP)") from None
    L = instaloader.Instaloader(download_pictures=False, download_videos=False, save_metadata=False, quiet=True)
    if session_user := session_user or config.env("INSTALOADER_SESSION_USER"):
        L.load_session_from_file(session_user)
    prof = instaloader.Profile.from_username(L.context, handle.lstrip("@"))
    posts = []
    for i, p in enumerate(prof.get_posts()):
        if i >= limit:
            break
        posts.append({
            "id": p.shortcode, "url": f"https://www.instagram.com/p/{p.shortcode}/", "title": None,
            "description": p.caption, "published_at": p.date_utc.replace(tzinfo=timezone.utc).isoformat(),
            "duration": p.video_duration, "views": p.video_view_count, "likes": p.likes,
            "comments": p.comments, "shares": None, "tags": list(p.caption_hashtags),
            "type": p.typename, "is_video": p.is_video,
        })
    return {"service": "instagram", "source": "instaloader", "url": f"https://www.instagram.com/{prof.username}/",
            "handle": prof.username, "name": prof.full_name, "bio": prof.biography,
            "external_url": prof.external_url, "followers": prof.followers, "following": prof.followees,
            "post_count": prof.mediacount, "is_business": prof.is_business_account,
            "category": prof.business_category_name, "posts": posts}


def discover(url: str, account: str | None = None, limit: int = 30, competitor: bool = False) -> dict:
    svc = detect_service(url)
    if svc == "instagram" and not re.search(r"/(p|reel|reels|tv)/", url):
        handle = re.sub(r"^https?://(www\.)?instagram\.com/", "", url).strip("/").split("/")[0]
        data = instaloader_profile(handle, limit)
    elif svc in ("youtube", "tiktok", "twitter", "instagram", "facebook", "threads", "bluesky"):
        data = ytdlp_profile(url, limit)
    else:
        raise SystemExit(f"no free extractor for {svc}: use Apify MCP / Firecrawl (see AGENTS.md › Discovery)")
    data["captured_at"] = store.now()

    db = store.connect()
    for p in data["posts"]:
        db.execute("INSERT OR REPLACE INTO public_posts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (data["service"], p["id"], account, data["handle"], int(competitor), p["url"], p.get("title"),
                    p.get("description"), p.get("published_at"), p.get("duration"), p.get("views"), p.get("likes"),
                    p.get("comments"), p.get("shares"), None, json.dumps(p), store.today()))
    for metric in ("followers", "following", "post_count"):
        if data.get(metric) is not None:
            # competitors are kept apart so they never blend into the client's own follower trend
            owner = (f"competitor:{account}" if competitor else account) or ""
            db.execute("INSERT OR REPLACE INTO account_metrics VALUES (?,?,?,?,?,?,?)",
                       (owner, data["service"], data["handle"], store.today(), metric, data[metric], data["source"]))
    db.commit()

    if account:
        d = config.account_dir(account) / "discovery"
        d.mkdir(exist_ok=True)
        name = f"{'competitor__' if competitor else ''}{data['service']}__{re.sub(r'[^\w.-]', '_', str(data['handle']))}.json"
        (d / name).write_text(json.dumps(data, indent=2, default=str))
        data["saved_to"] = str((d / name).relative_to(config.ROOT))
    return data


def summarize(data: dict) -> dict:
    """Compact stats an agent can reason over without reading every caption."""
    ps = [p for p in data["posts"] if p.get("published_at")]
    ps.sort(key=lambda p: p["published_at"])
    gaps = []
    for a, b in zip(ps, ps[1:]):
        try:
            gaps.append((datetime.fromisoformat(b["published_at"]) - datetime.fromisoformat(a["published_at"])).days)
        except ValueError:
            pass
    views = sorted(p["views"] for p in data["posts"] if p.get("views") is not None)
    top = sorted((p for p in data["posts"] if p.get("views")), key=lambda p: -p["views"])[:5]
    return {
        "service": data["service"], "handle": data["handle"], "name": data.get("name"), "followers": data.get("followers"),
        "posts_sampled": len(data["posts"]),
        "median_days_between_posts": sorted(gaps)[len(gaps) // 2] if gaps else None,
        "median_views": views[len(views) // 2] if views else None,
        "top_by_views": [{"url": p["url"], "views": p["views"], "title": (p.get("title") or p.get("description") or "")[:120]} for p in top],
        "saved_to": data.get("saved_to"),
    }
