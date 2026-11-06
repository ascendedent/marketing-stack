"""Deterministic pattern finding over the local store.

Every model (Claude, GPT, Grok) gets the same numbers from here; the agent's job is to interpret them,
not to recompute them. Principles (learned from the borghei analyzer, socials-assistant weekly-digest,
and the social-media-skills METER framework):

- Medians, not means: one viral post should not move the baseline.
- Normalize per channel: a post's score is its KPI divided by its channel's median ("lift").
  LinkedIn page vs personal profile vs Instagram are not comparable in raw numbers.
- A missing metric is not zero. Posts without the KPI are excluded, never zero-filled.
- Small samples lie: every bucket carries n and a `low_n` flag (n < 5).
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, store

ENGAGEMENT_PARTS = ["reactions", "likes", "comments", "shares", "reposts", "saves", "quotes"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def kpi_value(m: dict, kpi: str) -> float | None:
    if kpi == "engagementRate":
        if "engagementRate" in m:
            return m["engagementRate"]
        denom = m.get("reach") or m.get("impressions") or m.get("views")
        if not denom:
            return None
        return 100 * sum(m.get(k, 0) for k in ENGAGEMENT_PARTS if k != "likes" or "reactions" not in m) / denom
    if kpi == "engagements":
        parts = [m[k] for k in ENGAGEMENT_PARTS if k in m and not (k == "likes" and "reactions" in m)]
        return sum(parts) if parts else None
    return m.get(kpi)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _bucket_len(n: int) -> str:
    for edge, label in [(80, "<80"), (200, "80-199"), (500, "200-499"), (1000, "500-999"), (1500, "1000-1499")]:
        if n < edge:
            return label
    return "1500+"


def _hour_band(h: int) -> str:
    return f"{h // 3 * 3:02d}-{h // 3 * 3 + 3:02d}h"


def _summ(vals: list[float]) -> dict:
    return {"n": len(vals), "median_lift": round(statistics.median(vals), 2) if vals else None, "low_n": len(vals) < 5}


def report(account: str | None = None, days: int = 90, kpi: str = "engagementRate", tz: str | None = None,
           min_age_hours: int = 48) -> dict:
    db = store.connect()
    rows = store.latest_post_metrics(db, account)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    too_fresh = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
    zone = ZoneInfo(tz or (config.load_account(account).get("timezone") if account else None) or config.env("SMA_TIMEZONE"))

    posts = []
    for r in rows:
        sent = _parse(r["sent_at"])
        if not sent or sent < since or sent > too_fresh:
            continue
        v = kpi_value(r["metrics"], kpi)
        posts.append({**r, "sent": sent.astimezone(zone), "kpi": v})

    by_channel: dict[str, list] = defaultdict(list)
    for p in posts:
        by_channel[p["channel_id"]].append(p)

    channels = []
    for cid, ps in by_channel.items():
        vals = [p["kpi"] for p in ps if p["kpi"] is not None]
        med = statistics.median(vals) if vals else None
        for p in ps:
            p["lift"] = (p["kpi"] / med) if (med and p["kpi"] is not None) else None
        weeks = max(days / 7, 1)
        totals = defaultdict(float)
        for p in ps:
            for k, v in p["metrics"].items():
                if k != "engagementRate":
                    totals[k] += v
        channels.append({
            "channel_id": cid, "service": ps[0]["service"], "name": ps[0]["channel_name"], "type": ps[0]["channel_type"],
            "posts": len(ps), "posts_per_week": round(len(ps) / weeks, 2), "with_kpi": len(vals),
            "kpi_median": round(med, 3) if med is not None else None,
            "kpi_p90": round(sorted(vals)[int(0.9 * (len(vals) - 1))], 3) if vals else None,
            "totals": {k: round(v, 1) for k, v in sorted(totals.items())},
            "metrics_seen": sorted({k for p in ps for k in p["metrics"]}),
        })

    scored = [p for p in posts if p.get("lift") is not None]

    def breakdown(keyfn) -> dict:
        b: dict[str, list] = defaultdict(list)
        for p in scored:
            for k in (keyfn(p) if isinstance(keyfn(p), list) else [keyfn(p)]):
                b[str(k)].append(p["lift"])
        return {k: _summ(v) for k, v in sorted(b.items(), key=lambda kv: -statistics.median(kv[1]))}

    tags = defaultdict(list)
    for p in scored:
        for h in json.loads(p["hashtags"] or "[]"):
            tags[h].append(p["lift"])

    def brief(p):
        return {"id": p["id"], "service": p["service"], "channel": p["channel_name"], "sent": p["sent"].isoformat(),
                "kpi": round(p["kpi"], 3), "lift": round(p["lift"], 2), "post_type": p["post_type"],
                "media": p["media_kind"], "text_len": p["text_len"], "link": p["external_link"],
                "text": (p["text"] or "")[:280], "metrics": p["metrics"]}

    ranked = sorted(scored, key=lambda p: -p["lift"])

    # weekly trend (all channels, lift-normalized so mixed channels are comparable)
    weekly: dict[str, list] = defaultdict(list)
    for p in scored:
        wk = (p["sent"] - timedelta(days=p["sent"].weekday())).date().isoformat()
        weekly[wk].append(p["lift"])
    trend = [{"week_of": w, "posts": len(v), "median_lift": round(statistics.median(v), 2)} for w, v in sorted(weekly.items())]
    recent = [p["lift"] for p in scored if p["sent"] >= datetime.now(zone) - timedelta(days=28)]
    prior = [p["lift"] for p in scored if datetime.now(zone) - timedelta(days=56) <= p["sent"] < datetime.now(zone) - timedelta(days=28)]

    account_level = _account_level(db, account, days) if account else {}

    return {
        "account": account, "window_days": days, "kpi": kpi, "timezone": str(zone), "account_level": account_level,
        "generated_at": store.now(), "posts_in_window": len(posts), "posts_scored": len(scored),
        "notes": [
            "lift = post KPI / its channel's median KPI over the window (1.0 = typical).",
            "Buckets with low_n=true are anecdotes, not patterns.",
            f"Posts younger than {min_age_hours}h are excluded (metrics still accruing; Buffer refreshes ~daily).",
        ],
        "channels": channels,
        "by_weekday": breakdown(lambda p: WEEKDAYS[p["sent"].weekday()]),
        "by_hour_band": breakdown(lambda p: _hour_band(p["sent"].hour)),
        "by_post_type": breakdown(lambda p: p["post_type"] or "unknown"),
        "by_media": breakdown(lambda p: p["media_kind"]),
        "by_text_length": breakdown(lambda p: _bucket_len(p["text_len"] or 0)),
        "by_has_question": breakdown(lambda p: bool(p["has_question"])),
        "by_has_link": breakdown(lambda p: bool(p["has_link"])),
        "by_hashtag_count": breakdown(lambda p: min(len(json.loads(p["hashtags"] or "[]")), 5)),
        "hashtags": {h: _summ(v) for h, v in sorted(tags.items(), key=lambda kv: -statistics.median(kv[1])) if len(v) >= 3},
        "top_posts": [brief(p) for p in ranked[:5]],
        "bottom_posts": [brief(p) for p in ranked[-5:][::-1]] if len(ranked) > 5 else [],
        "outliers": [brief(p) for p in ranked if p["lift"] >= 3],
        "weekly_trend": trend,
        "scored_posts": [{"id": p["id"], "channel": p["channel_name"], "sent": p["sent"].isoformat(),
                          "kpi": round(p["kpi"], 3), "lift": round(p["lift"], 2)} for p in ranked],
        "last_28d_vs_prior_28d": {"recent": _summ(recent), "prior": _summ(prior)},
    }


def _account_level(db, account: str, days: int) -> dict:
    """Followers trend, audience and traffic per service from account_metrics (discovery + connectors + imports)."""
    out: dict = {}
    since = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    for (svc,) in db.execute("SELECT DISTINCT service FROM account_metrics WHERE account=?", (account,)).fetchall():
        f = db.execute("""SELECT captured_on, value FROM account_metrics WHERE account=? AND service=? AND metric='followers'
                          ORDER BY captured_on""", (account, svc)).fetchall()
        in_win = [r for r in f if r["captured_on"] >= since]
        entry: dict = {}
        if f:
            entry["followers"] = f[-1]["value"]
            entry["followers_as_of"] = f[-1]["captured_on"]
            if len(in_win) >= 2:
                entry["followers_change"] = in_win[-1]["value"] - in_win[0]["value"]
                entry["followers_change_since"] = in_win[0]["captured_on"]
        for prefix, key in (("audience:", "audience"), ("traffic:", "traffic")):
            rows = db.execute(f"""SELECT metric, value FROM account_metrics WHERE account=? AND service=? AND metric LIKE ?
                                  AND captured_on=(SELECT max(captured_on) FROM account_metrics WHERE account=? AND service=? AND metric LIKE ?)
                                  ORDER BY value DESC LIMIT 8""", (account, svc, prefix + "%", account, svc, prefix + "%")).fetchall()
            if rows:
                entry[key] = {r["metric"].removeprefix(prefix): r["value"] for r in rows}
        gained = db.execute("""SELECT sum(value) FROM account_metrics WHERE account=? AND service=? AND
                               metric IN ('subscribersGained','followers_gained') AND captured_on>=?""", (account, svc, since)).fetchone()[0]
        if gained is not None:
            entry["followers_gained_in_window"] = gained
        if entry:
            out[svc] = entry
    return out


def to_markdown(r: dict) -> str:
    out = [f"# Performance report — {r['account'] or 'all accounts'}",
           f"Window: last {r['window_days']} days · KPI: `{r['kpi']}` · tz {r['timezone']} · "
           f"{r['posts_scored']}/{r['posts_in_window']} posts scored · generated {r['generated_at']}", ""]
    out += ["## Channels", "| channel | service | posts | /wk | KPI median | KPI p90 | metrics seen |", "|---|---|---|---|---|---|---|"]
    for c in r["channels"]:
        out.append(f"| {c['name']} ({c['type']}) | {c['service']} | {c['posts']} | {c['posts_per_week']} | "
                   f"{c['kpi_median']} | {c['kpi_p90']} | {', '.join(c['metrics_seen'])} |")
    if r.get("account_level"):
        out += ["", "## Account level"]
        for svc, e in r["account_level"].items():
            line = f"- **{svc}**: followers {e.get('followers', '—')}"
            if "followers_change" in e:
                line += f" ({e['followers_change']:+.0f} since {e['followers_change_since']})"
            if "followers_gained_in_window" in e:
                line += f" · gained in window {e['followers_gained_in_window']:.0f}"
            out.append(line)
            for k in ("traffic", "audience"):
                if e.get(k):
                    out.append(f"  - {k}: " + ", ".join(f"{a} {b:g}" for a, b in list(e[k].items())[:6]))
    for title, key in [("Weekday", "by_weekday"), ("Hour band", "by_hour_band"), ("Post type", "by_post_type"),
                       ("Media", "by_media"), ("Text length", "by_text_length"), ("Asks a question", "by_has_question"),
                       ("Has link", "by_has_link"), ("Hashtag count", "by_hashtag_count"), ("Hashtags (n≥3)", "hashtags")]:
        if not r[key]:
            continue
        out += ["", f"## {title} (median lift)", "| bucket | n | lift |", "|---|---|---|"]
        out += [f"| {k} | {v['n']}{' ⚠' if v['low_n'] else ''} | {v['median_lift']} |" for k, v in r[key].items()]
    for title, key in [("Top posts", "top_posts"), ("Bottom posts", "bottom_posts")]:
        if r[key]:
            out += ["", f"## {title}"]
            out += [f"- **{p['lift']}×** {p['sent'][:16]} {p['channel']} [{p['post_type']}/{p['media']}, {p['text_len']}ch] "
                    f"— {p['text'][:140].replace(chr(10), ' ')}{' ' + p['link'] if p['link'] else ''}" for p in r[key]]
    lr = r["last_28d_vs_prior_28d"]
    out += ["", "## Trend", f"Last 28d median lift {lr['recent']['median_lift']} (n={lr['recent']['n']}) vs prior 28d "
            f"{lr['prior']['median_lift']} (n={lr['prior']['n']})."]
    out += ["", "_⚠ = n<5, treat as anecdote._"]
    return "\n".join(out)
