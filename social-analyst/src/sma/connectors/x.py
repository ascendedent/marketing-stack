"""X (Twitter) API v2 for an owned account — OAuth 2.0 user context (PKCE).

Adds what Buffer can't: bookmarks, quote counts, URL link clicks and profile clicks (private metrics
for posts < 30 days old), plus follower count over time. Setup: docs/connect-x.md.
X API access is pay-per-use: every post read is billed. `sync` caps reads (`max_posts`, default 200)
and requests private metrics only for posts inside X's 30-day window.

Fields (X API v2): public_metrics {retweet_count, reply_count, like_count, quote_count, bookmark_count,
impression_count}; non_public_metrics {impression_count, url_link_clicks, user_profile_clicks}
(owner only, < 30 days).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from .. import config, store
from . import oauth

API = "https://api.x.com/2"
AUTH_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
SCOPES = ["tweet.read", "users.read", "offline.access"]


def _client():
    cid = config.secret("X_CLIENT_ID")
    if not cid:
        raise SystemExit("X_CLIENT_ID not set — follow docs/connect-x.md, then `uv run sma setup keys --only X_CLIENT_ID,X_CLIENT_SECRET`.")
    return cid, config.secret("X_CLIENT_SECRET")


def connect(slug: str) -> dict:
    cid, secret = _client()
    tok = oauth.authorize(auth_url=AUTH_URL, token_url=TOKEN_URL, client_id=cid, client_secret=secret,
                          scopes=SCOPES, pkce=True, basic_auth=True)
    me = _get(tok["access_token"], "users/me", **{"user.fields": "username,name,public_metrics"})["data"]
    tok.update(user_id=me["id"], username=me["username"])
    oauth.save_token("x", slug, tok)
    acct = config.load_account(slug)
    acct.setdefault("connectors", {})["x"] = {"user_id": me["id"], "username": me["username"],
                                             "token": str(oauth.token_path("x", slug).relative_to(config.ROOT)),
                                             "connected_at": store.now()}
    config.save_account(slug, acct)
    return acct["connectors"]["x"]


def _get(token: str, path: str, **params) -> dict:
    r = httpx.get(f"{API}/{path}", params=params, headers={"authorization": f"Bearer {token}"}, timeout=60)
    if r.status_code == 429:
        raise RuntimeError(f"X rate limit; resets at {r.headers.get('x-rate-limit-reset')}")
    if r.status_code >= 400:
        raise RuntimeError(config.redact(f"X API {r.status_code}: {r.text[:300]}"))
    return r.json()


def _token(slug: str) -> dict:
    tok = oauth.load_token("x", slug)
    if oauth.expiring(tok):
        cid, secret = _client()
        new = oauth.refresh(token_url=TOKEN_URL, tok=tok, client_id=cid, client_secret=secret, basic_auth=True)
        if not new:
            raise SystemExit(f"X token expired and refresh failed — `uv run sma connect x {slug}`")
        tok.update(new)
        tok.pop("expires_at", None)
        oauth.save_token("x", slug, tok)
    return tok


def _timeline(token: str, uid: str, start: datetime, end: datetime | None, fields: str, cap: int) -> list[dict]:
    out, page = [], None
    while len(out) < cap:
        params = {"max_results": min(100, max(5, cap - len(out))), "exclude": "retweets,replies",
                  "tweet.fields": fields, "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ")}
        if end:
            params["end_time"] = end.strftime("%Y-%m-%dT%H:%M:%SZ")
        if page:
            params["pagination_token"] = page
        d = _get(token, f"users/{uid}/tweets", **params)
        out += d.get("data", [])
        page = (d.get("meta") or {}).get("next_token")
        if not page:
            break
    return out[:cap]


def sync(slug: str, days: int = 90, max_posts: int = 200) -> dict:
    tok = _token(slug)
    token, uid, handle = tok["access_token"], tok["user_id"], tok.get("username", "")
    db = store.connect()
    warnings: list[str] = []
    me = _get(token, "users/me", **{"user.fields": "public_metrics"})["data"]
    pm = me.get("public_metrics", {})
    for k, m in (("followers_count", "followers"), ("following_count", "following"), ("tweet_count", "post_count")):
        store.put_account_metric(db, slug, "twitter", handle, m, pm.get(k))
    channel_id = store.native_channel_id(db, slug, "twitter", uid, handle)

    now = datetime.now(timezone.utc)
    recent_start = now - timedelta(days=29)          # private metrics only exist inside 30 days
    base = "created_at,public_metrics,attachments,entities,conversation_id"
    posts = _timeline(token, uid, max(recent_start, now - timedelta(days=days)), None, base + ",non_public_metrics", max_posts)
    if days > 29 and len(posts) < max_posts:
        try:
            posts += _timeline(token, uid, now - timedelta(days=days), recent_start, base, max_posts - len(posts))
        except RuntimeError as e:
            warnings.append(f"older posts: {e}")

    for t in posts:
        p, n = t.get("public_metrics", {}), t.get("non_public_metrics", {})
        impressions = n.get("impression_count", p.get("impression_count"))
        metrics = {"impressions": impressions, "reactions": p.get("like_count"), "comments": p.get("reply_count"),
                   "reposts": p.get("retweet_count"), "quotes": p.get("quote_count"), "saves": p.get("bookmark_count"),
                   "clicks": n.get("url_link_clicks"), "profileClicks": n.get("user_profile_clicks")}
        if impressions:
            eng = sum(metrics[k] or 0 for k in ("reactions", "comments", "reposts", "quotes", "saves", "clicks", "profileClicks"))
            metrics["engagementRate"] = 100 * eng / impressions
        media = (t.get("attachments") or {}).get("media_keys")
        store.upsert_native_post(db, account=slug, service="twitter", native_id=t["id"], channel_id=channel_id,
                                 sent_at=t["created_at"], text=t.get("text"),
                                 url=f"https://x.com/{handle}/status/{t['id']}", post_type="post",
                                 media_kind="media" if media else "text", metrics=metrics, raw={"id": t["id"]})
    db.commit()
    return {"posts": len(posts), "billed_reads_estimate": len(posts) + 1, "warnings": warnings}
