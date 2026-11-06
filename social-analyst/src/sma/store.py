"""Local SQLite store. Agents analyze this, not live APIs (Buffer's rate limit is shared by every key/MCP).

Metrics are stored long-format per snapshot so growth curves and week-over-week deltas are possible:
a post synced daily accumulates one row per (post, metric, capture day).
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
  id TEXT PRIMARY KEY,            -- Buffer channel id
  account TEXT,                   -- accounts/<slug>
  login TEXT, organization_id TEXT, service TEXT, type TEXT, name TEXT, display_name TEXT,
  timezone TEXT, external_link TEXT, is_disconnected INTEGER, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS posts (
  id TEXT PRIMARY KEY,            -- Buffer post id
  account TEXT, channel_id TEXT, service TEXT, status TEXT, post_type TEXT,
  text TEXT, text_len INTEGER, hashtags TEXT, has_link INTEGER, has_question INTEGER, emoji_count INTEGER,
  media_kind TEXT, media_count INTEGER,
  created_at TEXT, due_at TEXT, sent_at TEXT, external_link TEXT, tags TEXT,
  metrics_updated_at TEXT, raw TEXT, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_posts_acct ON posts(account, sent_at);
CREATE TABLE IF NOT EXISTS post_metrics (
  post_id TEXT, captured_on TEXT, metric TEXT, value REAL, unit TEXT,
  PRIMARY KEY (post_id, captured_on, metric)
);
-- account-level numbers (followers etc.) from discovery or first-party APIs
CREATE TABLE IF NOT EXISTS account_metrics (
  account TEXT, service TEXT, handle TEXT, captured_on TEXT, metric TEXT, value REAL, source TEXT,
  PRIMARY KEY (account, service, handle, captured_on, metric)
);
-- public posts pulled by discovery (own history beyond Buffer, or competitors)
CREATE TABLE IF NOT EXISTS public_posts (
  service TEXT, id TEXT, account TEXT, handle TEXT, is_competitor INTEGER,
  url TEXT, title TEXT, description TEXT, published_at TEXT, duration REAL,
  views REAL, likes REAL, comments REAL, shares REAL, saves REAL,
  raw TEXT, captured_on TEXT,
  PRIMARY KEY (service, id)
);
-- per-day native series that only make sense summed (e.g. YouTube thumbnail impressions from Reporting API)
CREATE TABLE IF NOT EXISTS native_daily (
  post_id TEXT, day TEXT, metric TEXT, value REAL, PRIMARY KEY (post_id, day, metric)
);
CREATE TABLE IF NOT EXISTS video_analyses (
  key TEXT PRIMARY KEY,           -- service:id or sha1 of local file
  account TEXT, url TEXT, post_id TEXT, model TEXT, created_at TEXT, analysis TEXT
);
"""

_HASHTAG = re.compile(r"(?<!\w)#(\w{2,})", re.UNICODE)
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")


def connect() -> sqlite3.Connection:
    config.DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(config.DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def text_features(text: str) -> dict:
    text = text or ""
    return {
        "text_len": len(text),
        "hashtags": json.dumps(sorted({h.lower() for h in _HASHTAG.findall(text)})),
        "has_link": int(bool(re.search(r"https?://", text))),
        "has_question": int("?" in text),
        "emoji_count": len(_EMOJI.findall(text)),
    }


def upsert_channel(db, ch, account: str | None):
    db.execute(
        """INSERT INTO channels VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET account=coalesce(excluded.account, channels.account), login=excluded.login,
             service=excluded.service, type=excluded.type, name=excluded.name, display_name=excluded.display_name,
             timezone=excluded.timezone, external_link=excluded.external_link,
             is_disconnected=excluded.is_disconnected, updated_at=excluded.updated_at""",
        (ch.id, account, ch.login, ch.organization_id, ch.service, ch.type, ch.name, ch.display_name,
         ch.timezone, ch.external_link, int(ch.is_disconnected), now()))


def upsert_post(db, p: dict, account: str | None):
    assets = p.get("assets") or []
    kinds = sorted({a.get("type") for a in assets if a.get("type")})
    feats = text_features(p.get("text", ""))
    db.execute(
        """INSERT INTO posts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET status=excluded.status, text=excluded.text, text_len=excluded.text_len,
             hashtags=excluded.hashtags, has_link=excluded.has_link, has_question=excluded.has_question,
             emoji_count=excluded.emoji_count, media_kind=excluded.media_kind, media_count=excluded.media_count,
             due_at=excluded.due_at, sent_at=excluded.sent_at, external_link=excluded.external_link,
             tags=excluded.tags, metrics_updated_at=excluded.metrics_updated_at, raw=excluded.raw,
             updated_at=excluded.updated_at, account=coalesce(excluded.account, posts.account)""",
        (p["id"], account, p.get("channelId"), p.get("channelService"), p.get("status"),
         (p.get("metadata") or {}).get("type"), p.get("text"), feats["text_len"], feats["hashtags"],
         feats["has_link"], feats["has_question"], feats["emoji_count"],
         "+".join(kinds) if kinds else "text", len(assets),
         p.get("createdAt"), p.get("dueAt"), p.get("sentAt"), p.get("externalLink"),
         json.dumps([t["name"] for t in p.get("tags") or []]), p.get("metricsUpdatedAt"),
         json.dumps(p), now()))
    for m in p.get("metrics") or []:
        db.execute("INSERT OR REPLACE INTO post_metrics VALUES (?,?,?,?,?)",
                   (p["id"], today(), m["type"], m["value"], m["unit"]))


def latest_post_metrics(db, account: str | None = None) -> list[dict]:
    """One row per sent post with its newest value for every metric (wide)."""
    where = "WHERE p.status='sent'" + (" AND p.account=?" if account else "")
    rows = db.execute(f"""
      SELECT p.*, c.name AS channel_name, c.type AS channel_type, c.timezone AS channel_tz
      FROM posts p LEFT JOIN channels c ON c.id = p.channel_id {where}
      ORDER BY p.sent_at DESC""", (account,) if account else ()).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d.pop("raw", None)
        ms = db.execute("""SELECT metric, value FROM post_metrics WHERE post_id=? AND captured_on =
                           (SELECT max(captured_on) FROM post_metrics WHERE post_id=?)""", (r["id"], r["id"]))
        d["metrics"] = {m["metric"]: m["value"] for m in ms}
        out.append(d)
    return out


# ---- native (first-party API / export) data -------------------------------------
# Native posts land in the same `posts`/`post_metrics` tables as Buffer posts so `sma report` sees
# them. If a Buffer post already points at the same native post (externalLink contains the native
# id), metrics attach to the Buffer post instead of creating a duplicate.

def native_channel_id(db, account: str, service: str, native_key: str, name: str | None = None) -> str:
    """Reuse the account's linked Buffer channel for this service when there is exactly one."""
    rows = db.execute("SELECT id FROM channels WHERE account=? AND service=? AND login!='native'",
                      (account, service)).fetchall()
    if len(rows) == 1:
        return rows[0]["id"]
    cid = f"{service}:{native_key}"
    db.execute("""INSERT INTO channels (id, account, login, service, type, name, display_name, updated_at)
                  VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at""",
               (cid, account, "native", service, "native", name or native_key, name, now()))
    return cid


def upsert_native_post(db, *, account: str, service: str, native_id: str, channel_id: str, sent_at: str | None,
                       text: str | None, url: str | None, post_type: str | None, media_kind: str,
                       metrics: dict[str, float | None], raw: dict | None = None) -> str:
    match = db.execute("SELECT id FROM posts WHERE account=? AND service=? AND id NOT LIKE ? AND instr(coalesce(external_link,''), ?) > 0",
                       (account, service, f"{service}:%", native_id)).fetchone()
    post_id = match["id"] if match else f"{service}:{native_id}"
    if not match:
        feats = text_features(text or "")
        db.execute(
            """INSERT INTO posts (id, account, channel_id, service, status, post_type, text, text_len, hashtags, has_link,
                 has_question, emoji_count, media_kind, media_count, created_at, sent_at, external_link, raw, updated_at)
               VALUES (?,?,?,?,'sent',?,?,?,?,?,?,?,?,1,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET text=excluded.text, text_len=excluded.text_len, hashtags=excluded.hashtags,
                 post_type=excluded.post_type, raw=excluded.raw, updated_at=excluded.updated_at, channel_id=excluded.channel_id""",
            (post_id, account, channel_id, service, post_type, text, feats["text_len"], feats["hashtags"],
             feats["has_link"], feats["has_question"], feats["emoji_count"], media_kind, sent_at, sent_at, url,
             json.dumps(raw or {}, default=str), now()))
    for k, v in metrics.items():
        if v is not None:
            db.execute("INSERT OR REPLACE INTO post_metrics VALUES (?,?,?,?,?)",
                       (post_id, today(), k, float(v), "percentage" if k in PERCENT_METRICS else "count"))
    return post_id


PERCENT_METRICS = {"engagementRate", "averageViewPercentage", "completionRate", "retentionHook", "thumbnailCtr",
                   "retention25", "retention50", "retention75", "retentionEnd"}


def put_account_metric(db, account: str, service: str, handle: str, metric: str, value, *,
                       day: str | None = None, source: str = "api"):
    if value is None:
        return
    db.execute("INSERT OR REPLACE INTO account_metrics VALUES (?,?,?,?,?,?,?)",
               (account, service, handle or "", day or today(), metric, float(value), source))
