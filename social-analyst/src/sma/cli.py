"""`sma` — the one CLI every agent uses. Output is JSON unless a command says otherwise."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config, store


def out(obj):
    print(json.dumps(obj, indent=2, default=str))


# ---- account -----------------------------------------------------------------

def cmd_account_new(a):
    dst = config.ACCOUNTS / a.slug
    if dst.exists():
        sys.exit(f"accounts/{a.slug} already exists")
    shutil.copytree(config.ACCOUNTS / "_template", dst)
    acct = json.loads((dst / "account.json").read_text())
    acct.update(slug=a.slug, name=a.name or a.slug, created_at=store.now())
    (dst / "account.json").write_text(json.dumps(acct, indent=2))
    out({"created": f"accounts/{a.slug}", "next": "run the `onboard-account` skill"})


def cmd_account_list(a):
    out([{"slug": s, **{k: v for k, v in config.load_account(s).items() if k in ("name", "purpose", "status")}}
         for s in config.list_accounts()])


# ---- buffer ------------------------------------------------------------------

def _buffers(login: str | None):
    from .buffer import Buffer
    logins = [login] if login else sorted(config.buffer_logins())
    if not logins:
        sys.exit("no Buffer key configured — see docs/buffer-setup.md")
    return [Buffer(l) for l in logins]


def cmd_buffer_channels(a):
    rows = []
    for b in _buffers(a.login):
        for c in b.channels():
            rows.append(vars(c))
    out(rows)


def cmd_buffer_link(a):
    """Attach Buffer channels to an account so sync/report/post know which channels are 'this account'."""
    acct = config.load_account(a.slug)
    known = {c.id: c for b in _buffers(None) for c in b.channels()}
    db = store.connect()
    for cid in a.channel:
        if cid not in known:
            sys.exit(f"channel {cid} not visible to any configured Buffer key (run `sma buffer channels`)")
        c = known[cid]
        acct.setdefault("channels", [])
        acct["channels"] = [x for x in acct["channels"] if x["buffer_channel_id"] != cid] + [{
            "buffer_channel_id": c.id, "buffer_login": c.login, "organization_id": c.organization_id,
            "service": c.service, "type": c.type, "name": c.name, "display_name": c.display_name,
            "timezone": c.timezone}]
        store.upsert_channel(db, c, a.slug)
        if acct.get("timezone") in (None, "", "UTC") and c.timezone:
            acct["timezone"] = c.timezone  # bucket weekday/hour in the channel's local time
    db.commit()
    (config.account_dir(a.slug) / "account.json").write_text(json.dumps(acct, indent=2))
    out({"linked": [c["name"] for c in acct["channels"]]})


def _account_channels(slug: str) -> list[dict]:
    chs = config.load_account(slug).get("channels") or []
    if not chs:
        sys.exit(f"account {slug} has no Buffer channels linked — `sma buffer link {slug} --channel <id>`")
    return chs


def _resolve_channel(slug: str, want: str) -> dict:
    chs = _account_channels(slug)
    hits = [c for c in chs if want in (c["buffer_channel_id"], c["name"], c["service"], f"{c['service']}:{c['type']}")]
    if len(hits) != 1:
        sys.exit(f"--channel '{want}' matched {len(hits)} of: " + ", ".join(f"{c['service']}:{c['type']} {c['name']}" for c in chs))
    return hits[0]


# connector key in account.json → module in sma.connectors (linkedin covers linkedin_member + linkedin_org)
CONNECTOR_MODULES = {"youtube": "youtube", "instagram": "instagram", "threads": "threads", "x": "x", "linkedin": "linkedin"}


def cmd_sync(a):
    from .buffer import Buffer
    slugs = [a.slug] if a.slug else [x for x in config.list_accounts() if config.load_account(x).get("status") != "paused"]
    since = (datetime.now(timezone.utc) - timedelta(days=a.days)).isoformat()
    db = store.connect()
    summary = {}
    for slug in slugs:
        chs = config.load_account(slug).get("channels") or []
        groups: dict[tuple, list] = {}
        for c in chs:
            groups.setdefault((c["buffer_login"], c["organization_id"]), []).append(c["buffer_channel_id"])
        n = 0
        for (login, org), ids in groups.items():
            b = Buffer(login)
            for c in b.channels():
                if c.id in ids:
                    store.upsert_channel(db, c, slug)
            for p in b.posts(org, channel_ids=ids, status=a.status.split(","), since=since, limit=a.limit):
                store.upsert_post(db, p, slug)
                n += 1
        db.commit()
        summary[slug] = {"buffer_posts": n, "buffer_channels": len(chs)}
        if not a.buffer_only:
            conns = config.load_account(slug).get("connectors") or {}
            for name, module in CONNECTOR_MODULES.items():
                if any(k == name or k.startswith(name + "_") for k in conns):
                    try:
                        mod = __import__(f"sma.connectors.{module}", fromlist=["sync"])
                        summary[slug][name] = mod.sync(slug, days=a.days)
                    except (Exception, SystemExit) as e:
                        summary[slug][name] = {"error": config.redact(str(e))[:300]}
    out(summary)


def cmd_posts(a):
    db = store.connect()
    q = "SELECT id, service, status, post_type, media_kind, sent_at, due_at, external_link, substr(text,1,200) AS text FROM posts WHERE account=?"
    args = [a.slug]
    if a.status:
        q += " AND status=?"
        args.append(a.status)
    q += " ORDER BY coalesce(sent_at, due_at) DESC LIMIT ?"
    args.append(a.limit)
    out([dict(r) for r in db.execute(q, args)])


def cmd_report(a):
    from . import analyze
    r = analyze.report(a.slug, a.days, a.kpi)
    if a.save:
        d = config.account_dir(a.slug) / "reports"
        d.mkdir(exist_ok=True)
        stamp = store.today()
        (d / f"{stamp}-performance.json").write_text(json.dumps(r, indent=2, default=str))
        (d / f"{stamp}-performance.md").write_text(analyze.to_markdown(r))
    print(json.dumps(r, indent=2, default=str) if a.json else analyze.to_markdown(r))


def cmd_aggregate(a):
    from .buffer import Buffer
    chs = _account_channels(a.slug)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=a.days)
    res = []
    for c in chs:
        m = Buffer(c["buffer_login"]).aggregated_metrics(c["organization_id"], start.isoformat(), end.isoformat(), [c["buffer_channel_id"]])
        res.append({"channel": c["name"], "service": c["service"], **m})
    out(res)


def cmd_schedule_info(a):
    from .buffer import Buffer
    res = []
    for c in _account_channels(a.slug):
        b = Buffer(c["buffer_login"])
        info = b.posting_schedule(c["buffer_channel_id"])
        info["daily_limit"] = b.daily_limits([c["buffer_channel_id"]])
        res.append(info)
    out(res)


def _text(a) -> str:
    if a.text_file:
        return Path(a.text_file).read_text().strip()
    if a.text:
        return a.text
    return sys.stdin.read().strip()


def cmd_idea(a):
    """Default safe write: a Buffer Idea on the Create board. Not a post, not a publish."""
    from .buffer import Buffer, check_length
    c = _resolve_channel(a.slug, a.channel)
    text = _text(a)
    check_length(c["service"], text)
    acct = config.load_account(a.slug)
    title = a.title or f"{acct.get('name', a.slug)} · {c['service']} · {text[:40]}"
    res = Buffer(c["buffer_login"]).create_idea(
        organization_id=c["organization_id"], text=text, title=title, group_name=a.column,
        services=[c["service"]], date=a.date, image_urls=a.image, dry_run=a.dry_run)
    out(res)


def cmd_post(a):
    """Create a Buffer post. Draft by default. Queue/schedule need --no-draft. --now needs --yes too."""
    from .buffer import Buffer, check_length
    c = _resolve_channel(a.slug, a.channel)
    text = _text(a)
    check_length(c["service"], text)
    mode = "customScheduled" if a.at else "shareNext" if a.next else "shareNow" if a.now else "addToQueue"
    res = Buffer(c["buffer_login"]).create_post(
        channel_id=c["buffer_channel_id"], text=text, mode=mode, due_at=a.at,
        save_to_draft=not a.no_draft, images=a.image, videos=a.video, needs_approval=a.needs_approval,
        confirm_publish_now=bool(a.now and a.yes), dry_run=a.dry_run)
    out(res)


def cmd_delete_post(a):
    from .buffer import Buffer
    for b in _buffers(None):
        try:
            b.delete_post(a.id)
            return out({"deleted": a.id, "login": b.login})
        except Exception as e:  # try the next login
            last = str(e)
    sys.exit(f"delete failed on every login: {last}")


# ---- discovery & video -------------------------------------------------------

def cmd_discover(a):
    from . import discover
    data = discover.discover(a.url, a.account, a.limit, a.competitor)
    out(data if a.full else discover.summarize(data))


def cmd_video(a):
    from . import video
    rec = video.analyze(a.source, account=a.account, post_id=a.post_id, context=a.context or "",
                        direct=a.direct, force=a.force)
    if a.markdown and "analysis" in rec:
        print(video.to_markdown(rec))
    else:
        out(rec)


def cmd_download(a):
    from . import video
    out({"path": str(video.download(a.url))})


def cmd_doctor(a):  # kept for muscle memory; `sma setup status` is the full checklist
    import importlib.util
    checks = {
        "buffer_logins": sorted(config.buffer_logins()) or "MISSING — docs/buffer-setup.md",
        "gemini_key": bool(config.secret("GEMINI_API_KEY") or config.secret("GOOGLE_API_KEY")) or "MISSING — needed for `sma video`",
        "gemini_video_model": config.env("GEMINI_VIDEO_MODEL"),
        "apify_token": bool(config.secret("APIFY_TOKEN")) or "optional (Apify MCP discovery)",
        "ffmpeg": bool(shutil.which("ffmpeg")) or "MISSING — yt-dlp needs it to merge audio/video",
        "instaloader": bool(importlib.util.find_spec("instaloader")) or "optional: `uv sync --extra instagram`",
        "accounts": config.list_accounts(),
        "db": str(config.DB_PATH.relative_to(config.ROOT)),
    }
    if a.live:
        for login in config.buffer_logins():
            try:
                from .buffer import Buffer
                checks[f"buffer[{login}]"] = f"{len(Buffer(login).channels())} channels"
            except Exception as e:
                checks[f"buffer[{login}]"] = f"ERROR {e}"
    out(checks)


# ---- setup / connectors ------------------------------------------------------

def cmd_setup_status(a):
    from . import setup
    st = setup.status(live=a.live)
    print(setup.brief(st) if a.brief else json.dumps(st, indent=2, default=str))


def cmd_setup_init(a):
    from . import setup
    out(setup.init())


def cmd_setup_keys(a):
    from . import setup
    names = a.only.split(",") if a.only else None
    out(setup.key_form(names, timeout=a.timeout, open_browser=not a.no_browser))


def cmd_setup_set_key(a):
    from . import setup
    out(setup.set_key_from_stdin(a.name))


def cmd_setup_gemini(a):
    from . import setup
    res = setup.fix_gemini_model() if a.fix else setup.gemini_models()
    if a.test:
        res["test"] = setup.test_video()
    out(res)


def cmd_setup_schedule(a):
    from . import setup
    out(setup.schedule(a.at, a.remove))


def cmd_connect(a):
    from .connectors import instagram, linkedin, threads, x, youtube
    if a.service == "youtube":
        out(youtube.connect(a.slug))
    elif a.service == "instagram":
        out(instagram.connect(a.slug, a.token_env or "INSTAGRAM_ACCESS_TOKEN", a.host))
    elif a.service == "threads":
        out(threads.connect(a.slug, a.token_env or "THREADS_ACCESS_TOKEN"))
    elif a.service == "x":
        out(x.connect(a.slug))
    elif a.service == "linkedin":
        if a.mode == "org" and not a.org_id:
            sys.exit("--mode org needs --org-id (the number in linkedin.com/company/<id>/admin, or from the Page URN)")
        out(linkedin.connect(a.slug, a.mode, a.org_id))


def cmd_import(a):
    from .connectors import tiktok_import
    out(tiktok_import.import_file(a.slug, a.file, a.kind))


def cmd_ig_lookup(a):
    from .connectors import instagram
    bd = instagram.business_discovery(a.slug, a.username, a.limit)
    out({k: v for k, v in bd.items() if k != "media"} | {"media_count_fetched": len((bd.get("media") or {}).get("data", []))})


def cmd_account_metrics(a):
    db = store.connect()
    q = "SELECT service, handle, captured_on, metric, value, source FROM account_metrics WHERE account=?"
    args = [a.slug]
    if a.metric:
        q += " AND metric LIKE ?"
        args.append(a.metric.replace("*", "%"))
    q += " ORDER BY captured_on DESC, metric LIMIT ?"
    args.append(a.limit)
    out([dict(r) for r in db.execute(q, args)])


# ---- wiring ------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(prog="sma", description="Social media analyst toolkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("doctor", help="check keys/tools (names only, never values)")
    s.add_argument("--live", action="store_true", help="also call Buffer (read-only)")
    s.set_defaults(fn=cmd_doctor)

    st = sub.add_parser("setup", help="agent-driven first-run setup").add_subparsers(dest="sub", required=True)
    s = st.add_parser("status", help="ordered checklist + next_step"); s.add_argument("--live", action="store_true")
    s.add_argument("--brief", action="store_true"); s.set_defaults(fn=cmd_setup_status)
    s = st.add_parser("init", help="create .env, data dirs, MCP configs"); s.set_defaults(fn=cmd_setup_init)
    s = st.add_parser("keys", help="one-shot local web form to paste keys into .env (never via chat)")
    s.add_argument("--only", help="comma-separated key names"); s.add_argument("--timeout", type=int, default=900)
    s.add_argument("--no-browser", action="store_true"); s.set_defaults(fn=cmd_setup_keys)
    s = st.add_parser("set-key", help="hidden terminal prompt for one key"); s.add_argument("name"); s.set_defaults(fn=cmd_setup_set_key)
    s = st.add_parser("gemini", help="list models / fix GEMINI_VIDEO_MODEL / self-test")
    s.add_argument("--fix", action="store_true"); s.add_argument("--test", action="store_true"); s.set_defaults(fn=cmd_setup_gemini)
    s = st.add_parser("schedule", help="install daily `sma sync` (systemd user timer / launchd / cron line)")
    s.add_argument("--at", default="06:30"); s.add_argument("--remove", action="store_true"); s.set_defaults(fn=cmd_setup_schedule)

    s = sub.add_parser("connect", help="first-party analytics: youtube | instagram | threads | x | linkedin (docs/connect-*.md)")
    s.add_argument("service", choices=["youtube", "instagram", "threads", "x", "linkedin"]); s.add_argument("slug")
    s.add_argument("--token-env", help="env var holding the token (instagram/threads)")
    s.add_argument("--host", default="instagram", choices=["instagram", "facebook"], help="instagram only")
    s.add_argument("--mode", default="member", choices=["member", "org"], help="linkedin: personal posts or a Page")
    s.add_argument("--org-id", help="linkedin --mode org: organization id")
    s.set_defaults(fn=cmd_connect)
    imp = sub.add_parser("import").add_subparsers(dest="sub", required=True)
    s = imp.add_parser("tiktok", help="TikTok Studio export (CSV/XLSX)"); s.add_argument("slug"); s.add_argument("file")
    s.add_argument("--kind", choices=["content", "overview", "followers", "other"]); s.set_defaults(fn=cmd_import)
    s = sub.add_parser("ig-lookup", help="public stats of another IG business account (needs facebook-host token)")
    s.add_argument("slug"); s.add_argument("username"); s.add_argument("--limit", type=int, default=25); s.set_defaults(fn=cmd_ig_lookup)
    s = sub.add_parser("account-metrics", help="followers, daily trend, audience, traffic (account level)")
    s.add_argument("slug"); s.add_argument("--metric", help="filter, * wildcard e.g. 'audience:*'"); s.add_argument("--limit", type=int, default=100)
    s.set_defaults(fn=cmd_account_metrics)

    acc = sub.add_parser("account").add_subparsers(dest="sub", required=True)
    s = acc.add_parser("new"); s.add_argument("slug"); s.add_argument("--name"); s.set_defaults(fn=cmd_account_new)
    s = acc.add_parser("list"); s.set_defaults(fn=cmd_account_list)

    buf = sub.add_parser("buffer").add_subparsers(dest="sub", required=True)
    s = buf.add_parser("channels"); s.add_argument("--login"); s.set_defaults(fn=cmd_buffer_channels)
    s = buf.add_parser("link"); s.add_argument("slug"); s.add_argument("--channel", action="append", required=True)
    s.set_defaults(fn=cmd_buffer_link)

    s = sub.add_parser("sync", help="pull posts + metrics from Buffer into the local store")
    s.add_argument("slug", nargs="?"); s.add_argument("--days", type=int, default=180)
    s.add_argument("--status", default="sent,scheduled,draft"); s.add_argument("--limit", type=int, default=1000)
    s.add_argument("--buffer-only", action="store_true", help="skip YouTube/Instagram connectors"); s.set_defaults(fn=cmd_sync)

    s = sub.add_parser("posts"); s.add_argument("slug"); s.add_argument("--status"); s.add_argument("--limit", type=int, default=30)
    s.set_defaults(fn=cmd_posts)

    s = sub.add_parser("report", help="pattern report from the local store (markdown; --json for raw)")
    s.add_argument("slug"); s.add_argument("--days", type=int, default=90); s.add_argument("--kpi", default="engagementRate")
    s.add_argument("--json", action="store_true"); s.add_argument("--save", action="store_true")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("aggregate", help="Buffer aggregatedPostMetrics per linked channel")
    s.add_argument("slug"); s.add_argument("--days", type=int, default=30); s.set_defaults(fn=cmd_aggregate)

    s = sub.add_parser("schedule-info", help="posting schedule slots + daily limits per channel")
    s.add_argument("slug"); s.set_defaults(fn=cmd_schedule_info)

    for name, fn, hlp in [("idea", cmd_idea, "add a Buffer Idea to the Create board (default safe write)"),
                          ("post", cmd_post, "create a Buffer post (draft unless --no-draft)")]:
        s = sub.add_parser(name, help=hlp)
        s.add_argument("slug"); s.add_argument("--channel", required=True, help="channel id, name, service, or service:type")
        s.add_argument("--text"); s.add_argument("--text-file")
        s.add_argument("--image", action="append"); s.add_argument("--dry-run", action="store_true")
        if name == "idea":
            s.add_argument("--title"); s.add_argument("--date", help="intended slot, ISO-8601 UTC")
            s.add_argument("--column", default="In Progress", help="Create-board column name")
        else:
            s.add_argument("--video", action="append")
            s.add_argument("--no-draft", action="store_true", help="really queue/schedule instead of saving as draft")
            g = s.add_mutually_exclusive_group()
            g.add_argument("--at", help="customScheduled time, ISO-8601 UTC")
            g.add_argument("--next", action="store_true", help="shareNext (top of queue)")
            g.add_argument("--now", action="store_true", help="shareNow — requires --yes and explicit user instruction")
            s.add_argument("--yes", action="store_true"); s.add_argument("--needs-approval", action="store_true")
        s.set_defaults(fn=fn)

    s = sub.add_parser("delete-post"); s.add_argument("id"); s.set_defaults(fn=cmd_delete_post)

    s = sub.add_parser("discover", help="pull a public profile's metadata + recent posts (yt-dlp / instaloader)")
    s.add_argument("url"); s.add_argument("--account"); s.add_argument("--limit", type=int, default=30)
    s.add_argument("--competitor", action="store_true"); s.add_argument("--full", action="store_true")
    s.set_defaults(fn=cmd_discover)

    s = sub.add_parser("video", help="download (if needed) + Gemini structured breakdown")
    s.add_argument("source", help="URL or local file"); s.add_argument("--account"); s.add_argument("--post-id")
    s.add_argument("--context"); s.add_argument("--direct", action="store_true", help="pass public YouTube URL straight to Gemini")
    s.add_argument("--force", action="store_true"); s.add_argument("--markdown", action="store_true")
    s.set_defaults(fn=cmd_video)

    s = sub.add_parser("download"); s.add_argument("url"); s.set_defaults(fn=cmd_download)

    a = p.parse_args(argv)
    try:
        a.fn(a)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        sys.exit(config.redact(f"error: {e}"))


if __name__ == "__main__":
    main()
