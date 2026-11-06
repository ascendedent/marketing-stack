"""Threads API (graph.threads.net) insights for an owned profile.

Adds what Buffer's basic Threads analytics lack: per-post views, likes, replies, reposts, quotes,
shares; account views/clicks over time, follower count, follower demographics. Setup:
docs/connect-threads.md. Long-lived tokens last 60 days; `sync` refreshes after 30.
Ported from joeswann/threads-mcp (see docs/sources.md).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx

from .. import config, store

BASE = "https://graph.threads.net"
POST_METRICS = ["views", "likes", "replies", "reposts", "quotes", "shares"]
USER_METRICS = ["views", "likes", "replies", "reposts", "quotes", "clicks", "followers_count"]


def _version() -> str:
    return config.env("THREADS_API_VERSION", "v1.0")


def _token_path(slug: str):
    return config.TOKENS / f"threads__{slug}.json"


def _get(token: str, path: str, **params) -> dict:
    r = httpx.get(f"{BASE}/{_version()}/{path}", params={**params, "access_token": token}, timeout=60)
    body = r.json() if "json" in r.headers.get("content-type", "") else {}
    if r.status_code >= 400 or "error" in body:
        raise RuntimeError(config.redact(f"Threads {r.status_code}: {(body.get('error') or {}).get('message') or r.text[:300]}"))
    return body


def connect(slug: str, token_env: str = "THREADS_ACCESS_TOKEN") -> dict:
    token = config.secret(token_env)
    if not token:
        raise SystemExit(f"{token_env} not set — docs/connect-threads.md, then `uv run sma setup keys --only {token_env}`.")
    me = _get(token, "me", fields="id,username")
    config.write_private(_token_path(slug), json.dumps({"access_token": token, "user_id": me["id"],
                                                        "username": me["username"], "refreshed_at": store.now()}))
    acct = config.load_account(slug)
    acct.setdefault("connectors", {})["threads"] = {"user_id": me["id"], "username": me["username"],
                                                   "token": str(_token_path(slug).relative_to(config.ROOT)),
                                                   "connected_at": store.now()}
    config.save_account(slug, acct)
    return acct["connectors"]["threads"]


def _load(slug: str) -> dict:
    p = _token_path(slug)
    if not p.exists():
        raise SystemExit(f"Threads not connected for {slug}: `uv run sma connect threads {slug}`")
    tok = json.loads(p.read_text())
    config._SECRETS.add(tok["access_token"])
    age = datetime.now(timezone.utc) - datetime.fromisoformat(tok.get("refreshed_at", "2000-01-01T00:00:00+00:00"))
    if age > timedelta(days=30):
        r = httpx.get(f"{BASE}/refresh_access_token", params={"grant_type": "th_refresh_token",
                                                              "access_token": tok["access_token"]}, timeout=60)
        if r.status_code == 200 and "access_token" in r.json():
            tok.update(access_token=r.json()["access_token"], refreshed_at=store.now())
            config.write_private(p, json.dumps(tok))
    return tok


def _val(d: dict):
    if "total_value" in d:
        return d["total_value"].get("value")
    vals = d.get("values") or []
    return sum(v.get("value", 0) for v in vals) if vals else None


def sync(slug: str, days: int = 90, max_posts: int = 200) -> dict:
    tok = _load(slug)
    token, uid, handle = tok["access_token"], tok["user_id"], tok.get("username", "")
    db = store.connect()
    warnings = []
    channel_id = store.native_channel_id(db, slug, "threads", uid, handle)
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    posts, after = [], None
    while len(posts) < max_posts:
        d = _get(token, "me/threads", fields="id,text,media_type,permalink,timestamp,shortcode,is_quote_post",
                 since=since, limit=50, **({"after": after} if after else {}))
        posts += d.get("data", [])
        after = ((d.get("paging") or {}).get("cursors") or {}).get("after")
        if not d.get("data") or not after:
            break

    for p in posts[:max_posts]:
        if p.get("media_type") == "REPOST_FACADE":
            continue
        try:
            ins = {i["name"]: _val(i) for i in _get(token, f"{p['id']}/insights", metric=",".join(POST_METRICS)).get("data", [])}
        except RuntimeError as e:
            warnings.append(f"{p['id']}: {str(e)[:120]}")
            ins = {}
        metrics = {"views": ins.get("views"), "reactions": ins.get("likes"), "comments": ins.get("replies"),
                   "reposts": ins.get("reposts"), "quotes": ins.get("quotes"), "shares": ins.get("shares")}
        if metrics["views"]:
            eng = sum(metrics[k] or 0 for k in ("reactions", "comments", "reposts", "quotes", "shares"))
            metrics["engagementRate"] = 100 * eng / metrics["views"]
        mt = p.get("media_type", "TEXT_POST")
        store.upsert_native_post(
            db, account=slug, service="threads", native_id=p.get("shortcode") or p["id"], channel_id=channel_id,
            sent_at=(p.get("timestamp") or "").replace("+0000", "+00:00") or None, text=p.get("text"), url=p.get("permalink"),
            post_type="post", media_kind={"TEXT_POST": "text", "IMAGE": "image", "VIDEO": "video",
                                          "CAROUSEL_ALBUM": "carousel"}.get(mt, "text"),
            metrics=metrics, raw={"id": p["id"], "media_type": mt, "quote": p.get("is_quote_post")})

    until = int(datetime.now(timezone.utc).timestamp())
    try:
        for i in _get(token, "me/threads_insights", metric=",".join(USER_METRICS),
                      since=until - 29 * 86400, until=until).get("data", []):
            if i["name"] == "followers_count":
                store.put_account_metric(db, slug, "threads", handle, "followers", _val(i))
            elif i.get("values"):
                for v in i["values"]:
                    store.put_account_metric(db, slug, "threads", handle, f"daily_{i['name']}", v.get("value"),
                                             day=(v.get("end_time") or store.today())[:10])
            else:
                store.put_account_metric(db, slug, "threads", handle, f"30d_{i['name']}", _val(i))
    except RuntimeError as e:
        warnings.append(f"account insights: {str(e)[:160]}")
    for breakdown in ("country", "city", "age", "gender"):
        try:
            d = _get(token, "me/threads_insights", metric="follower_demographics", breakdown=breakdown).get("data", [])
            for res in (d[0]["total_value"]["breakdowns"][0]["results"] if d else []):
                store.put_account_metric(db, slug, "threads", handle,
                                         f"audience:{breakdown}:{'_'.join(res['dimension_values'])}", res["value"])
        except (RuntimeError, KeyError, IndexError) as e:
            warnings.append(f"demographics: {str(e)[:120]}")
            break
    db.commit()
    return {"posts": len(posts), "warnings": warnings}
