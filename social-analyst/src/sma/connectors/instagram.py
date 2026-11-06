"""Instagram Graph API insights for an owned Business/Creator account.

Two token routes (docs/connect-instagram.md):
- "instagram" host (default): Instagram API with Instagram Login — graph.instagram.com, no Facebook
  Page needed. Long-lived token (60 days), auto-refreshed by `sync` when older than 30 days.
- "facebook" host: Instagram API with Facebook Login — graph.facebook.com via a linked Page. Needed
  for business_discovery (public stats of other business accounts → competitor scans).

Adds what Buffer can't: reach, saves, shares, total interactions, Reels average watch time and
completion rate, follower count over time, profile views, follower demographics.
Ported from adelaidasofia/instagram-mcp, sskghub/instagram-analytics-mcp, aryaminus/socials-assistant.
Metric names change between Graph versions: unknown metrics are dropped one by one, not fatal.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import httpx

from .. import config, store

HOSTS = {"instagram": "https://graph.instagram.com", "facebook": "https://graph.facebook.com"}
MEDIA_FIELDS = "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count,media_url"
FEED_METRICS = ["views", "reach", "saved", "shares", "total_interactions", "likes", "comments"]
REEL_METRICS = FEED_METRICS + ["ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]


def _version() -> str:
    return config.env("INSTAGRAM_GRAPH_VERSION", "v24.0")


def _token_path(slug: str):
    return config.TOKENS / f"instagram__{slug}.json"


class IG:
    def __init__(self, token: str, host: str = "instagram"):
        self.token, self.host = token, host
        config._SECRETS.add(token)
        self.base = f"{HOSTS[host]}/{_version()}"

    def get(self, path: str, **params) -> dict:
        r = httpx.get(f"{self.base}/{path.lstrip('/')}", params={**params, "access_token": self.token}, timeout=60)
        body = r.json() if r.headers.get("content-type", "").startswith(("application/json", "text/javascript")) else {}
        if r.status_code >= 400 or "error" in body:
            err = body.get("error", {})
            raise RuntimeError(config.redact(f"Graph {r.status_code}: {err.get('message') or r.text[:300]}"))
        return body

    def insights(self, obj_id: str, metrics: list[str], **params) -> tuple[dict, list[str]]:
        """Fetch metrics; on an 'invalid metric' error retry one by one and report what was dropped."""
        try:
            data = self.get(f"{obj_id}/insights", metric=",".join(metrics), **params).get("data", [])
            return {d["name"]: d for d in data}, []
        except RuntimeError:
            out, dropped = {}, []
            for m in metrics:
                try:
                    for d in self.get(f"{obj_id}/insights", metric=m, **params).get("data", []):
                        out[d["name"]] = d
                except RuntimeError:
                    dropped.append(m)
            return out, dropped


def _value(d: dict | None):
    if not d:
        return None
    if "total_value" in d:
        return d["total_value"].get("value")
    vals = d.get("values") or []
    return vals[-1].get("value") if vals else None


def _load_token(slug: str) -> tuple[str, dict]:
    p = _token_path(slug)
    if not p.exists():
        raise SystemExit(f"Instagram not connected for {slug}: `uv run sma connect instagram {slug}`")
    return json.loads(p.read_text())["access_token"], json.loads(p.read_text())


def connect(slug: str, token_env: str = "INSTAGRAM_ACCESS_TOKEN", host: str = "instagram") -> dict:
    token = config.secret(token_env)
    if not token:
        raise SystemExit(f"{token_env} is not set. Follow docs/connect-instagram.md, then `uv run sma setup keys`.")
    ig = IG(token, host)
    if host == "instagram":
        me = ig.get("me", fields="user_id,username,account_type")
        user_id, username = me.get("user_id") or me["id"], me["username"]
    else:
        pages = ig.get("me/accounts", fields="id,name,instagram_business_account{id,username}").get("data", [])
        linked = [p for p in pages if p.get("instagram_business_account")]
        if not linked:
            raise SystemExit("No Facebook Page with a linked Instagram business account on this token.")
        user_id, username = linked[0]["instagram_business_account"]["id"], linked[0]["instagram_business_account"]["username"]
    config.write_private(_token_path(slug), json.dumps({"access_token": token, "host": host, "user_id": user_id,
                                                        "username": username, "refreshed_at": store.now()}))
    acct = config.load_account(slug)
    acct.setdefault("connectors", {})["instagram"] = {"user_id": user_id, "username": username, "host": host,
                                                      "token": str(_token_path(slug).relative_to(config.ROOT)),
                                                      "connected_at": store.now()}
    config.save_account(slug, acct)
    return acct["connectors"]["instagram"]


def _maybe_refresh(slug: str, tok: dict) -> str:
    """Instagram-Login long-lived tokens last 60 days; refresh after 30 so they never lapse."""
    if tok.get("host", "instagram") != "instagram":
        return tok["access_token"]
    age = datetime.now(timezone.utc) - datetime.fromisoformat(tok.get("refreshed_at", "2000-01-01T00:00:00+00:00"))
    if age < timedelta(days=30):
        return tok["access_token"]
    r = httpx.get(f"{HOSTS['instagram']}/refresh_access_token",
                  params={"grant_type": "ig_refresh_token", "access_token": tok["access_token"]}, timeout=60)
    if r.status_code == 200 and "access_token" in r.json():
        tok.update(access_token=r.json()["access_token"], refreshed_at=store.now())
        config.write_private(_token_path(slug), json.dumps(tok))
    return tok["access_token"]


def _duration(url: str | None) -> float | None:
    if not url or not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", url],
                             capture_output=True, text=True, timeout=45)
        return float(out.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired):
        return None


def sync(slug: str, days: int = 180, max_media: int = 200, probe_duration: bool = True) -> dict:
    token, tok = _load_token(slug)
    token = _maybe_refresh(slug, tok)
    ig, uid = IG(token, tok.get("host", "instagram")), tok["user_id"]
    db = store.connect()
    warnings: list[str] = []
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)

    prof = ig.get(uid if ig.host == "facebook" else "me",
                  fields="username,followers_count,follows_count,media_count,biography,website")
    handle = prof.get("username", tok.get("username"))
    for k, m in (("followers_count", "followers"), ("follows_count", "following"), ("media_count", "post_count")):
        store.put_account_metric(db, slug, "instagram", handle, m, prof.get(k))
    channel_id = store.native_channel_id(db, slug, "instagram", str(uid), handle)

    media, after = [], None
    while len(media) < max_media:
        d = ig.get(f"{uid}/media", fields=MEDIA_FIELDS, limit=50, **({"after": after} if after else {}))
        batch = d.get("data", [])
        media += [m for m in batch if datetime.fromisoformat(m["timestamp"].replace("+0000", "+00:00")) >= since_dt]
        after = (d.get("paging") or {}).get("cursors", {}).get("after")
        if not batch or not after or datetime.fromisoformat(batch[-1]["timestamp"].replace("+0000", "+00:00")) < since_dt:
            break

    dropped_all: set[str] = set()
    for m in media[:max_media]:
        is_reel = m.get("media_product_type") == "REELS"
        if m.get("media_product_type") == "STORY":
            continue
        ins, dropped = ig.insights(m["id"], REEL_METRICS if is_reel else FEED_METRICS)
        dropped_all.update(dropped)
        metrics = {
            "views": _value(ins.get("views")), "reach": _value(ins.get("reach")), "saves": _value(ins.get("saved")),
            "shares": _value(ins.get("shares")), "totalInteractions": _value(ins.get("total_interactions")),
            "likes": _value(ins.get("likes")) or m.get("like_count"), "comments": _value(ins.get("comments")) or m.get("comments_count"),
        }
        if is_reel:
            avg_ms, tot_ms = _value(ins.get("ig_reels_avg_watch_time")), _value(ins.get("ig_reels_video_view_total_time"))
            metrics["averageTimeWatched"] = avg_ms / 1000 if avg_ms is not None else None
            metrics["totalTimeWatched"] = tot_ms / 60000 if tot_ms is not None else None
            if probe_duration and avg_ms and (dur := _duration(m.get("media_url"))):
                metrics["durationSeconds"] = dur
                metrics["completionRate"] = min(100.0, 100 * (avg_ms / 1000) / dur)
        if metrics["reach"] and metrics["totalInteractions"] is not None:
            metrics["engagementRate"] = 100 * metrics["totalInteractions"] / metrics["reach"]
        mt = m.get("media_type")
        store.upsert_native_post(
            db, account=slug, service="instagram", native_id=m["permalink"].rstrip("/").split("/")[-1],
            channel_id=channel_id, sent_at=m["timestamp"].replace("+0000", "+00:00"), text=m.get("caption"),
            url=m["permalink"], post_type={"REELS": "reel", "FEED": "carousel" if mt == "CAROUSEL_ALBUM" else "post"}.get(
                m.get("media_product_type"), "post"),
            media_kind={"VIDEO": "video", "IMAGE": "image", "CAROUSEL_ALBUM": "carousel"}.get(mt, "image"),
            metrics=metrics, raw={"id": m["id"], "media_type": mt, "product": m.get("media_product_type")})
    if dropped_all:
        warnings.append(f"metrics not available on Graph {_version()}: {sorted(dropped_all)}")

    # account daily (last 30 days max per call)
    until = int(datetime.now(timezone.utc).timestamp())
    since = until - 29 * 86400
    try:
        ins, dropped = ig.insights(uid, ["reach", "follower_count"], period="day", since=since, until=until)
        for name, d in ins.items():
            for v in d.get("values", []):
                store.put_account_metric(db, slug, "instagram", handle,
                                         "followers_gained" if name == "follower_count" else f"daily_{name}",
                                         v.get("value"), day=v["end_time"][:10])
        tot, dropped2 = ig.insights(uid, ["views", "profile_views", "accounts_engaged", "total_interactions"],
                                    period="day", metric_type="total_value", since=since, until=until)
        for name, d in tot.items():
            store.put_account_metric(db, slug, "instagram", handle, f"30d_{name}", _value(d))
        if dropped or dropped2:
            warnings.append(f"account insights dropped: {dropped + dropped2}")
    except RuntimeError as e:
        warnings.append(f"account insights: {e}")

    for breakdown in ("age", "gender", "country", "city"):
        try:
            d = ig.get(f"{uid}/insights", metric="follower_demographics", period="lifetime",
                       metric_type="total_value", breakdown=breakdown).get("data", [])
            for res in (d[0]["total_value"]["breakdowns"][0]["results"] if d else []):
                store.put_account_metric(db, slug, "instagram", handle,
                                         f"audience:{breakdown}:{'_'.join(res['dimension_values'])}", res["value"])
        except (RuntimeError, KeyError, IndexError) as e:
            warnings.append(f"demographics {breakdown}: {e}")
            break  # usually: < 100 followers, or missing permission — don't repeat the same error 4 times
    db.commit()
    return {"media": len(media), "warnings": warnings}


def business_discovery(slug: str, username: str, limit: int = 25) -> dict:
    """Public stats of another Business/Creator account (competitor scans). Needs the facebook host."""
    token, tok = _load_token(slug)
    if tok.get("host") != "facebook":
        raise SystemExit("business_discovery needs a Facebook-Login token (connect with --host facebook).")
    ig = IG(token, "facebook")
    f = (f"business_discovery.username({username.lstrip('@')}){{username,name,biography,followers_count,media_count,"
         f"media.limit({limit}){{id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count}}}}")
    bd = ig.get(tok["user_id"], fields=f)["business_discovery"]
    db = store.connect()
    store.put_account_metric(db, f"competitor:{slug}", "instagram", bd["username"], "followers", bd.get("followers_count"),
                             source="business_discovery")
    for m in (bd.get("media") or {}).get("data", []):
        db.execute("INSERT OR REPLACE INTO public_posts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   ("instagram", m["permalink"].rstrip("/").split("/")[-1], slug, bd["username"], 1, m["permalink"], None,
                    m.get("caption"), m["timestamp"], None, None, m.get("like_count"), m.get("comments_count"), None, None,
                    json.dumps(m), store.today()))
    db.commit()
    return bd
