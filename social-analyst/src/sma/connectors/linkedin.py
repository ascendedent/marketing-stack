"""LinkedIn Community Management API — member post analytics and organization (Page) analytics.

Adds what Buffer can't: for personal profiles, saves, sends, link clicks, followers and profile
views gained per post (r_member_postAnalytics); for Pages, unique impressions/clicks per post,
follower count over time and follower demographics (function, seniority, industry, country).
Setup: docs/connect-linkedin.md — needs a LinkedIn app with Community Management API access, which
LinkedIn reviews (requires a company page and a legal business).

Post URNs come from the Buffer posts already in the store (their externalLink is
https://www.linkedin.com/feed/update/urn:li:share:…), so no post-listing permission is needed.
Docs: learn.microsoft.com/linkedin/marketing/community-management (members/post-statistics,
organizations/share-statistics, organizations/follower-statistics).
"""

from __future__ import annotations

import re
from urllib.parse import quote

import httpx

from .. import config, store
from . import oauth

API = "https://api.linkedin.com/rest"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
MEMBER_SCOPES = ["r_member_postAnalytics"]
ORG_SCOPES = ["rw_organization_admin"]
MEMBER_METRICS = {"IMPRESSION": "impressions", "MEMBERS_REACHED": "reach", "RESHARE": "reposts", "REACTION": "reactions",
                  "COMMENT": "comments", "POST_SAVE": "saves", "POST_SEND": "sends", "LINK_CLICKS": "clicks",
                  "FOLLOWER_GAINED_FROM_CONTENT": "follows", "PROFILE_VIEW_FROM_CONTENT": "profileViews"}
URN = re.compile(r"urn:li:(share|ugcPost|activity):(\d+)")


def _version() -> str:
    return config.env("LINKEDIN_API_VERSION", "202610")


def _client():
    cid, secret = config.secret("LINKEDIN_CLIENT_ID"), config.secret("LINKEDIN_CLIENT_SECRET")
    if not (cid and secret):
        raise SystemExit("LINKEDIN_CLIENT_ID / LINKEDIN_CLIENT_SECRET not set — docs/connect-linkedin.md, then "
                         "`uv run sma setup keys --only LINKEDIN_CLIENT_ID,LINKEDIN_CLIENT_SECRET`.")
    return cid, secret


def _get(token: str, path: str, query: str = "") -> dict:
    """LinkedIn Rest.li 2.0 needs hand-built query strings (List(...), (start:(…))) — pass them raw."""
    r = httpx.get(f"{API}/{path}{'?' + query if query else ''}", timeout=60, headers={
        "authorization": f"Bearer {token}", "linkedin-version": _version(), "x-restli-protocol-version": "2.0.0"})
    if r.status_code >= 400:
        raise RuntimeError(config.redact(f"LinkedIn {r.status_code}: {r.text[:300]}"))
    return r.json()


def connect(slug: str, mode: str = "member", org_id: str | None = None) -> dict:
    """mode=member (personal profile posts) or org (a Page you administer; pass --org-id)."""
    cid, secret = _client()
    scopes = MEMBER_SCOPES if mode == "member" else ORG_SCOPES
    tok = oauth.authorize(auth_url=AUTH_URL, token_url=TOKEN_URL, client_id=cid, client_secret=secret,
                          scopes=scopes, pkce=False)
    tok.update(mode=mode, org_id=org_id)
    name = f"linkedin_{mode}"
    oauth.save_token(name, slug, tok)
    acct = config.load_account(slug)
    acct.setdefault("connectors", {})[name] = {"mode": mode, "org_id": org_id, "scopes": scopes,
                                               "token": str(oauth.token_path(name, slug).relative_to(config.ROOT)),
                                               "expires_at": tok.get("expires_at"), "connected_at": store.now()}
    config.save_account(slug, acct)
    return acct["connectors"][name]


def _token(slug: str, name: str) -> dict:
    tok = oauth.load_token(name, slug)
    if oauth.expiring(tok, within_s=3 * 86400):
        cid, secret = _client()
        new = oauth.refresh(token_url=TOKEN_URL, tok=tok, client_id=cid, client_secret=secret)
        if new:
            tok.update(new)
            tok.pop("expires_at", None)
            oauth.save_token(name, slug, tok)
        elif oauth.expiring(tok, within_s=0):
            raise SystemExit(f"LinkedIn token expired (60-day life, no refresh token) — `uv run sma connect linkedin {slug}`")
    return tok


def _posts(db, slug: str, channel_type: str) -> list[tuple[str, str, str]]:
    """(post_id, urn_kind, urn) for Buffer LinkedIn posts of this account on profile/page channels."""
    rows = db.execute("""SELECT p.id, p.external_link FROM posts p JOIN channels c ON c.id=p.channel_id
                         WHERE p.account=? AND p.service='linkedin' AND p.status='sent' AND c.type=?""",
                      (slug, channel_type)).fetchall()
    out = []
    for r in rows:
        if m := URN.search(r["external_link"] or ""):
            out.append((r["id"], m.group(1), f"urn:li:{m.group(1)}:{m.group(2)}"))
    return out


def _put(db, post_id: str, metrics: dict):
    for k, v in metrics.items():
        if v is not None:
            db.execute("INSERT OR REPLACE INTO post_metrics VALUES (?,?,?,?,?)",
                       (post_id, store.today(), k, float(v), "percentage" if k in store.PERCENT_METRICS else "count"))


def sync_member(slug: str, max_posts: int = 100) -> dict:
    tok = _token(slug, "linkedin_member")
    db = store.connect()
    warnings, n = [], 0
    for post_id, kind, urn in _posts(db, slug, "profile")[:max_posts]:
        if kind == "activity":
            warnings.append(f"{post_id}: activity URN can't be queried; skipped")
            continue
        ent = f"({'ugc' if kind == 'ugcPost' else 'share'}:{quote(urn, safe='')})"
        metrics = {}
        for q, name in MEMBER_METRICS.items():
            try:
                els = _get(tok["access_token"], "memberCreatorPostAnalytics",
                           f"q=entity&entity={ent}&queryType={q}&aggregation=TOTAL").get("elements", [])
                if els:
                    metrics[name] = els[0].get("count")
            except RuntimeError as e:
                if "403" in str(e):
                    raise SystemExit("LinkedIn refused r_member_postAnalytics — the app needs Community Management API "
                                     "access (docs/connect-linkedin.md §1).") from None
                warnings.append(f"{post_id} {q}: {str(e)[:120]}")
        if metrics.get("impressions"):
            eng = sum(metrics.get(k) or 0 for k in ("reactions", "comments", "reposts", "saves", "sends", "clicks"))
            metrics["engagementRate"] = 100 * eng / metrics["impressions"]
        _put(db, post_id, metrics)
        n += 1
    db.commit()
    return {"posts": n, "calls": n * len(MEMBER_METRICS), "warnings": warnings[:10]}


def sync_org(slug: str) -> dict:
    tok = _token(slug, "linkedin_org")
    org = tok.get("org_id") or (config.load_account(slug).get("connectors", {}).get("linkedin_org") or {}).get("org_id")
    if not org:
        raise SystemExit("no organization id — reconnect with `uv run sma connect linkedin <slug> --mode org --org-id <id>`")
    org_urn = f"urn:li:organization:{org}"
    enc = quote(org_urn, safe="")
    db = store.connect()
    warnings = []
    posts = _posts(db, slug, "page")
    n = 0
    for kind in ("share", "ugcPost"):
        batch = [(pid, urn) for pid, k, urn in posts if k == kind]
        for i in range(0, len(batch), 20):
            chunk = batch[i:i + 20]
            param = "shares" if kind == "share" else "ugcPosts"
            lst = ",".join(quote(u, safe="") for _, u in chunk)
            try:
                els = _get(tok["access_token"], "organizationalEntityShareStatistics",
                           f"q=organizationalEntity&organizationalEntity={enc}&{param}=List({lst})").get("elements", [])
            except RuntimeError as e:
                warnings.append(f"share stats: {str(e)[:160]}")
                continue
            by = {e.get(kind): e.get("totalShareStatistics", {}) for e in els}
            for pid, urn in chunk:
                s = by.get(urn, {})  # LinkedIn omits posts with no activity: all zeros
                _put(db, pid, {"impressions": s.get("impressionCount", 0), "reach": s.get("uniqueImpressionsCount"),
                               "clicks": s.get("clickCount", 0), "reactions": s.get("likeCount", 0),
                               "comments": s.get("commentCount", 0), "shares": s.get("shareCount", 0),
                               "engagementRate": 100 * s["engagement"] if s.get("engagement") is not None else None})
                n += 1
    try:
        size = _get(tok["access_token"], f"networkSizes/{enc}", "edgeType=COMPANY_FOLLOWED_BY_MEMBER")
        store.put_account_metric(db, slug, "linkedin", org, "followers", size.get("firstDegreeSize"))
    except RuntimeError as e:
        warnings.append(f"follower count: {str(e)[:160]}")
    try:
        els = _get(tok["access_token"], "organizationalEntityFollowerStatistics",
                   f"q=organizationalEntity&organizationalEntity={enc}").get("elements", [])
        for facet, key in (("followerCountsByFunction", "function"), ("followerCountsBySeniority", "seniority"),
                           ("followerCountsByIndustry", "industry"), ("followerCountsByGeoCountry", "geo"),
                           ("followerCountsByStaffCountRange", "staffCountRange")):
            for row in (els[0].get(facet, []) if els else []):
                label = next((str(v) for k, v in row.items() if k != "followerCounts"), "?")
                c = row.get("followerCounts", {})
                store.put_account_metric(db, slug, "linkedin", org, f"audience:{key}:{label.rsplit(':', 1)[-1]}",
                                         (c.get("organicFollowerCount") or 0) + (c.get("paidFollowerCount") or 0))
    except RuntimeError as e:
        warnings.append(f"follower demographics: {str(e)[:160]}")
    db.commit()
    return {"posts": n, "warnings": warnings}


def sync(slug: str, days: int = 0) -> dict:
    conns = config.load_account(slug).get("connectors") or {}
    out = {}
    if "linkedin_member" in conns:
        out["member"] = sync_member(slug)
    if "linkedin_org" in conns:
        out["org"] = sync_org(slug)
    return out
