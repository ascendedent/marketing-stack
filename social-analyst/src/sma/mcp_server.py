"""Local MCP server exposing the same toolkit as the `sma` CLI (stdio).

Use it from MCP clients that cannot run shell commands (Claude Desktop, ChatGPT desktop, Grok with MCP).
Agents with a shell can call `uv run sma ...` directly; both paths hit the same code and store.
Write tools default to the safe path (Idea / draft). Publishing now is deliberately not exposed here.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from mcp.server.mcpserver import MCPServer

from . import analyze, config, store

mcp = MCPServer("social-analyst", instructions="Social media analyst toolkit. Read account_profile(slug) before analysis or writing. Writes default to Buffer Ideas / drafts; never publish without the owner.")


@mcp.tool()
def setup_status(live: bool = False) -> dict:
    """First-run checklist with `next_step`. Call at the start of a session; follow the `setup` skill if incomplete."""
    from . import setup
    return setup.status(live=live)


@mcp.tool()
def account_metrics(slug: str, metric: str | None = None, limit: int = 100) -> list[dict]:
    """Account-level numbers: followers over time, daily trend, audience demographics, traffic sources.
    `metric` filters with * wildcards, e.g. 'audience:*' or 'followers'."""
    db = store.connect()
    q, args = "SELECT service, handle, captured_on, metric, value, source FROM account_metrics WHERE account=?", [slug]
    if metric:
        q += " AND metric LIKE ?"
        args.append(metric.replace("*", "%"))
    return [dict(r) for r in db.execute(q + " ORDER BY captured_on DESC, metric LIMIT ?", (*args, limit))]


@mcp.tool()
def import_tiktok_export(slug: str, file_path: str) -> dict:
    """Import a TikTok Studio export (CSV/XLSX) for an account."""
    from .connectors import tiktok_import
    return tiktok_import.import_file(slug, file_path)


@mcp.tool()
def list_accounts() -> list[dict]:
    """Accounts configured under accounts/ with their linked Buffer channels."""
    return [{"slug": s, **{k: v for k, v in config.load_account(s).items() if k in ("name", "purpose", "channels", "status")}}
            for s in config.list_accounts()]


@mcp.tool()
def account_profile(slug: str) -> str:
    """The account's onboarding profile (purpose, voice, audience, goals, guardrails) — read before any analysis or writing."""
    d = config.account_dir(slug)
    return "\n\n".join(p.read_text() for p in [d / "profile.md", d / "account.json"] if p.exists())


@mcp.tool()
def buffer_channels() -> list[dict]:
    """All Buffer channels visible to every configured Buffer key."""
    from .buffer import Buffer
    return [vars(c) for l in sorted(config.buffer_logins()) for c in Buffer(l).channels()]


@mcp.tool()
def sync_account(slug: str, days: int = 180) -> dict:
    """Pull posts + per-post metrics from Buffer, plus YouTube/Instagram insights if connected, into the local store."""
    from .cli import cmd_sync
    import argparse, io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_sync(argparse.Namespace(slug=slug, days=days, status="sent,scheduled,draft", limit=1000, buffer_only=False))
    return json.loads(buf.getvalue())


@mcp.tool()
def performance_report(slug: str, days: int = 90, kpi: str = "engagementRate") -> dict:
    """Deterministic pattern report (lift by weekday/hour/type/media/length/hashtags, top/bottom posts, trend)."""
    return analyze.report(slug, days, kpi)


@mcp.tool()
def recent_posts(slug: str, status: str = "sent", limit: int = 30) -> list[dict]:
    """Recent posts from the local store (run sync_account first)."""
    db = store.connect()
    return [dict(r) for r in db.execute(
        "SELECT id, service, status, post_type, media_kind, sent_at, due_at, external_link, text FROM posts "
        "WHERE account=? AND status=? ORDER BY coalesce(sent_at,due_at) DESC LIMIT ?", (slug, status, limit))]


@mcp.tool()
def discover_profile(url: str, account: str | None = None, limit: int = 30, competitor: bool = False) -> dict:
    """Public profile metadata + recent posts with counts (yt-dlp / instaloader). Saves under accounts/<slug>/discovery/."""
    from . import discover
    return discover.summarize(discover.discover(url, account, limit, competitor))


@mcp.tool()
def analyze_video(source: str, account: str | None = None, context: str = "", direct: bool = False) -> dict:
    """Download a social video (TikTok/Reels/Shorts/X/YouTube or local path) and return a Gemini breakdown:
    hook, scenes with timestamps, transcript, pacing, retention risks, improvements. Cached per source."""
    from . import video
    return video.analyze(source, account=account, context=context, direct=direct)


@mcp.tool()
def create_idea(slug: str, channel: str, text: str, title: str | None = None, date: str | None = None,
                dry_run: bool = False) -> dict:
    """Safe write: put copy on the Buffer Create board (column 'In Progress') as an Idea. Not a post."""
    from .buffer import Buffer, check_length
    from .cli import _resolve_channel
    c = _resolve_channel(slug, channel)
    check_length(c["service"], text)
    return Buffer(c["buffer_login"]).create_idea(
        organization_id=c["organization_id"], text=text, title=title or f"{slug} · {c['service']} · {text[:40]}",
        services=[c["service"]], date=date, dry_run=dry_run)


@mcp.tool()
def create_draft_post(slug: str, channel: str, text: str, scheduled_at: str | None = None,
                      image_urls: list[str] | None = None, video_urls: list[str] | None = None,
                      dry_run: bool = False) -> dict:
    """Create a Buffer DRAFT post (optionally with an intended time). Media URLs must be public HTTPS.
    Queueing for real / publishing is left to a human in Buffer or the CLI."""
    from .buffer import Buffer, check_length
    from .cli import _resolve_channel
    c = _resolve_channel(slug, channel)
    check_length(c["service"], text)
    return Buffer(c["buffer_login"]).create_post(
        channel_id=c["buffer_channel_id"], text=text, mode="customScheduled" if scheduled_at else "addToQueue",
        due_at=scheduled_at, save_to_draft=True, images=image_urls, videos=video_urls, dry_run=dry_run)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
