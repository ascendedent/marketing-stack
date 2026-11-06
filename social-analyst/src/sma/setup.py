"""First-run setup, designed to be driven by an agent.

`sma setup status` returns an ordered checklist with a single `next_step` so any model can walk the
owner through setup without reading code. Secrets never pass through the chat: `sma setup keys`
opens a one-shot local web form (127.0.0.1) where the owner pastes keys; values go straight to .env.
"""

from __future__ import annotations

import html
import importlib.util
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from . import config, store

# key name → (label, where to get it, required?, validator name)
KEYS = {
    "BUFFER_API_KEY": ("Buffer API key (main login)", "https://publish.buffer.com/settings/api", True, "buffer"),
    "GEMINI_API_KEY": ("Gemini API key (video breakdowns)", "https://aistudio.google.com/apikey", True, "gemini"),
    "APIFY_TOKEN": ("Apify token (optional: scraping profiles yt-dlp can't reach)", "https://console.apify.com/settings/integrations", False, None),
    "INSTAGRAM_ACCESS_TOKEN": ("Instagram access token (optional: deep IG insights)", "docs/connect-instagram.md", False, None),
    "GOOGLE_OAUTH_CLIENT_ID": ("Google OAuth client ID (optional: YouTube Analytics)", "docs/connect-youtube.md", False, None),
    "GOOGLE_OAUTH_CLIENT_SECRET": ("Google OAuth client secret (optional: YouTube Analytics)", "docs/connect-youtube.md", False, None),
    "THREADS_ACCESS_TOKEN": ("Threads access token (optional: Threads insights)", "docs/connect-threads.md", False, None),
    "X_CLIENT_ID": ("X OAuth 2.0 client ID (optional: X metrics, paid API)", "docs/connect-x.md", False, None),
    "X_CLIENT_SECRET": ("X OAuth 2.0 client secret (optional; blank for public clients)", "docs/connect-x.md", False, None),
    "LINKEDIN_CLIENT_ID": ("LinkedIn app client ID (optional: LinkedIn analytics)", "docs/connect-linkedin.md", False, None),
    "LINKEDIN_CLIENT_SECRET": ("LinkedIn app client secret (optional)", "docs/connect-linkedin.md", False, None),
}


# ---- validation ------------------------------------------------------------------

_VSTATE = lambda: config.DATA / ".key_checks.json"


def _fingerprint(v: str) -> str:
    import hashlib
    return hashlib.sha256(v.encode()).hexdigest()[:12]


def _remember(name: str, res: dict) -> dict:
    """Cache the last live check per key (by value fingerprint, never the value) for offline status."""
    v = config.secret(name)
    if v:
        try:
            st = json.loads(_VSTATE().read_text()) if _VSTATE().exists() else {}
        except ValueError:
            st = {}
        st[name] = {"fp": _fingerprint(v), "ok": res["ok"], "at": store.now(), "detail": str(res.get("detail", ""))[:160]}
        config.DATA.mkdir(parents=True, exist_ok=True)
        _VSTATE().write_text(json.dumps(st, indent=2))
    return res


def last_check(name: str) -> dict | None:
    v = config.secret(name)
    try:
        st = json.loads(_VSTATE().read_text()).get(name) if _VSTATE().exists() else None
    except ValueError:
        return None
    return st if (st and v and st["fp"] == _fingerprint(v)) else None


def validate(name: str) -> dict:
    return _remember(name, _validate(name))


def _validate(name: str) -> dict:
    config.reload_env()
    kind = KEYS.get(name, (None, None, None, "buffer" if name.startswith("BUFFER_API_KEY") else None))[3]
    if not config.secret(name):
        return {"key": name, "ok": False, "detail": "not set"}
    try:
        if kind == "buffer":
            from .buffer import Buffer
            label = "default" if name == "BUFFER_API_KEY" else name.removeprefix("BUFFER_API_KEY_").lower()
            chs = Buffer(label).channels()
            return {"key": name, "ok": True, "detail": f"{len(chs)} channels: " + ", ".join(f"{c.service}:{c.type} {c.name}" for c in chs)}
        if kind == "gemini":
            return {"key": name, "ok": True, **gemini_models()}
    except Exception as e:
        return {"key": name, "ok": False, "detail": config.redact(str(e))[:300]}
    return {"key": name, "ok": True, "detail": "set (no live check for this key)"}


def gemini_models() -> dict:
    from google import genai
    client = genai.Client(api_key=config.secret("GEMINI_API_KEY") or config.secret("GOOGLE_API_KEY"))
    names = []
    for m in client.models.list():
        acts = getattr(m, "supported_actions", None) or []
        if "generateContent" in acts and "gemini" in m.name and not any(x in m.name for x in ("embedding", "tts", "image", "live", "audio")):
            names.append(m.name.removeprefix("models/"))
    want = config.env("GEMINI_VIDEO_MODEL")

    def rank(n: str):
        import re
        v = [int(x) for x in re.findall(r"\d+", n.split("-")[1] if "-" in n else "0")] or [0]
        return ("flash" in n and "lite" not in n, "preview" not in n and "exp" not in n, v)
    best = max(names, key=rank) if names else None
    return {"configured": want, "configured_available": want in names, "suggested": best,
            "flash_models": sorted(n for n in names if "flash" in n)}


def fix_gemini_model() -> dict:
    info = gemini_models()
    if not info["configured_available"] and info["suggested"]:
        config.set_env_value("GEMINI_VIDEO_MODEL", info["suggested"])
        info["changed_to"] = info["suggested"]
    return info


def test_video() -> dict:
    """End-to-end Gemini check on a generated 3s test clip (no download, a few thousand tokens)."""
    from . import video
    clip = config.MEDIA / "_selftest.mp4"
    config.MEDIA.mkdir(parents=True, exist_ok=True)
    if not clip.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x568:rate=10",
                        "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-vf",
                        "drawtext=text='HOOK TEST':fontsize=36:x=(w-tw)/2:y=60:fontcolor=white",
                        "-shortest", "-pix_fmt", "yuv420p", str(clip)], check=False)
        if not clip.exists():  # drawtext may be missing from minimal ffmpeg builds
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x568:rate=10",
                            "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest", "-pix_fmt", "yuv420p", str(clip)], check=True)
    rec = video.analyze(str(clip), force=True, context="This is a synthetic test pattern used to check the pipeline.")
    a = rec["analysis"]
    return {"ok": True, "model": rec["model"], "tokens": rec.get("tokens"), "summary": a["summary"][:200],
            "scenes": len(a["scenes"])}


# ---- key entry form ----------------------------------------------------------------

def key_form(names: list[str] | None = None, timeout: int = 900, open_browser: bool = True) -> dict:
    """Serve a one-shot form on 127.0.0.1; write submitted values to .env; validate; exit."""
    names = names or list(KEYS)
    nonce = secrets.token_urlsafe(16)
    result: dict = {}
    done = threading.Event()

    def page(body: str) -> bytes:
        return f"""<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Social Analyst · keys</title><style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:640px;margin:40px auto;padding:0 16px;color:#1d1d1f;background:#fafafa}}
label{{display:block;margin:18px 0 4px;font-weight:600}} small{{color:#666;font-weight:400}}
input{{width:100%;padding:9px;border:1px solid #ccc;border-radius:8px;font:inherit;box-sizing:border-box}}
button{{margin-top:24px;padding:10px 18px;border:0;border-radius:8px;background:#111;color:#fff;font:inherit;cursor:pointer}}
.ok{{color:#0a7d2c}} .bad{{color:#b00020}} code{{background:#eee;padding:1px 4px;border-radius:4px}}
@media (prefers-color-scheme:dark){{body{{background:#161616;color:#eee}} input{{background:#222;color:#eee;border-color:#444}} small{{color:#aaa}} code{{background:#333}} button{{background:#eee;color:#111}}}}
</style>{body}""".encode()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            rows = []
            for n in names:
                label, where, req, _ = KEYS.get(n, (n, "", False, None))
                have = " <span class=ok>(already set — leave blank to keep)</span>" if config.secret(n) else ""
                link = f'<a href="{html.escape(where)}" target=_blank>get it</a>' if where.startswith("http") else f"see <code>{html.escape(where)}</code>"
                rows.append(f'<label>{html.escape(label)}{"" if req else " <small>optional</small>"}{have}<br><small>{n} · {link}</small></label>'
                            f'<input type=password name="{n}" autocomplete=off spellcheck=false>')
            body = (f"<h1>Connect your keys</h1><p>Values are written to <code>.env</code> in the project folder on this "
                    f"computer and never shown to the agent.</p><form method=post action='/{nonce}'>{''.join(rows)}"
                    f"<button>Save and check</button></form>")
            self.send_response(200); self.send_header("content-type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(page(body))

        def do_POST(self):
            if self.path != f"/{nonce}":
                self.send_response(403); self.end_headers(); return
            data = parse_qs(self.rfile.read(int(self.headers.get("content-length", 0))).decode())
            saved = []
            for n in names:
                v = (data.get(n) or [""])[0].strip()
                if v:
                    config.set_env_value(n, v)
                    saved.append(n)
            checks = [validate(n) for n in saved]
            result.update(saved=saved, checks=checks)
            items = "".join(f"<li class={'ok' if c['ok'] else 'bad'}>{c['key']}: {'✓' if c['ok'] else '✗'} "
                            f"{html.escape(str(c.get('detail') or c.get('configured') or ''))[:200]}</li>" for c in checks)
            self.send_response(200); self.send_header("content-type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(page(f"<h1>Saved {len(saved)} key(s)</h1><ul>{items or '<li>nothing entered</li>'}</ul>"
                                  f"<p>You can close this tab and go back to your agent.</p>"))
            done.set()

    srv = HTTPServer(("127.0.0.1", 0), H)
    url = f"http://127.0.0.1:{srv.server_port}/"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(json.dumps({"form_url": url, "waiting_seconds": timeout}), flush=True)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    finished = done.wait(timeout)
    srv.shutdown()
    return result if finished else {"timeout": True, "form_url": url}


def set_key_from_stdin(name: str) -> dict:
    """Fallback for terminals: `uv run sma setup set-key NAME` (hidden prompt) or piped stdin."""
    import getpass
    v = getpass.getpass(f"{name}: ") if sys.stdin.isatty() else sys.stdin.readline()
    v = v.strip()
    if not v:
        return {"key": name, "ok": False, "detail": "empty"}
    config.set_env_value(name, v)
    return validate(name)


# ---- daily sync scheduling ---------------------------------------------------------

import hashlib as _h
# one timer per project copy, so two checkouts never overwrite each other's schedule
UNIT = f"social-analyst-sync-{_h.sha1(str(config.ROOT).encode()).hexdigest()[:6]}"


def schedule(at: str = "06:30", remove: bool = False) -> dict:
    uv = shutil.which("uv") or "uv"
    cmd = f'{uv} run --directory "{config.ROOT}" sma sync'
    log = config.DATA / "sync.log"
    system = platform.system()
    if system == "Linux" and shutil.which("systemctl"):
        d = Path.home() / ".config/systemd/user"
        svc, tmr = d / f"{UNIT}.service", d / f"{UNIT}.timer"
        if remove:
            subprocess.run(["systemctl", "--user", "disable", "--now", f"{UNIT}.timer"], check=False)
            svc.unlink(missing_ok=True); tmr.unlink(missing_ok=True)
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
            return {"removed": True}
        d.mkdir(parents=True, exist_ok=True)
        svc.write_text(f"[Unit]\nDescription=Social Analyst daily sync\n\n[Service]\nType=oneshot\n"
                       f"WorkingDirectory={config.ROOT}\nExecStart=/bin/sh -c '{cmd} >> \"{log}\" 2>&1'\n")
        tmr.write_text(f"[Unit]\nDescription=Social Analyst daily sync\n\n[Timer]\nOnCalendar=*-*-* {at}:00\n"
                       f"Persistent=true\nRandomizedDelaySec=600\n\n[Install]\nWantedBy=timers.target\n")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        r = subprocess.run(["systemctl", "--user", "enable", "--now", f"{UNIT}.timer"], capture_output=True, text=True)
        return {"scheduler": "systemd --user", "at": at, "ok": r.returncode == 0, "detail": r.stderr.strip()[:200],
                "check": f"systemctl --user list-timers {UNIT}.timer", "log": str(log)}
    if system == "Darwin":
        plist = Path.home() / f"Library/LaunchAgents/com.{UNIT}.plist"
        if remove:
            subprocess.run(["launchctl", "unload", str(plist)], check=False)
            plist.unlink(missing_ok=True)
            return {"removed": True}
        h, m = at.split(":")
        plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>Label</key><string>com.{UNIT}</string>
<key>ProgramArguments</key><array><string>/bin/sh</string><string>-c</string><string>{html.escape(cmd)} &gt;&gt; "{log}" 2&gt;&amp;1</string></array>
<key>StartCalendarInterval</key><dict><key>Hour</key><integer>{int(h)}</integer><key>Minute</key><integer>{int(m)}</integer></dict>
</dict></plist>""")
        subprocess.run(["launchctl", "unload", str(plist)], check=False, capture_output=True)
        r = subprocess.run(["launchctl", "load", str(plist)], capture_output=True, text=True)
        return {"scheduler": "launchd", "at": at, "ok": r.returncode == 0, "plist": str(plist), "log": str(log)}
    h, m = at.split(":")
    return {"scheduler": "manual", "ok": False,
            "detail": f"Add this line with `crontab -e` (or Task Scheduler on Windows): {int(m)} {int(h)} * * * {cmd} >> {log} 2>&1"}


def schedule_installed() -> bool:
    if platform.system() == "Linux":
        return (Path.home() / f".config/systemd/user/{UNIT}.timer").exists()
    if platform.system() == "Darwin":
        return (Path.home() / f"Library/LaunchAgents/com.{UNIT}.plist").exists()
    try:
        return UNIT in subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout or "sma sync" in \
            subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return False


# ---- status ------------------------------------------------------------------------

def status(live: bool = False) -> dict:
    config.reload_env()
    steps: list[dict] = []

    def step(id_, ok, detail, nxt=None, required=True):
        steps.append({"id": id_, "ok": bool(ok), "required": required, "detail": detail, **({"next": nxt} if not ok and nxt else {})})

    step("tools", shutil.which("ffmpeg") and shutil.which("ffprobe"),
         "ffmpeg + ffprobe" if shutil.which("ffmpeg") else "ffmpeg missing",
         "Install ffmpeg (Fedora: `sudo dnf install ffmpeg`, Debian/Ubuntu: `sudo apt install ffmpeg`, macOS: `brew install ffmpeg`). Ask the owner before running sudo.")
    step("env_file", config.ENV_FILE.exists(), ".env present" if config.ENV_FILE.exists() else "no .env",
         "Run `uv run sma setup init`.")
    logins = config.buffer_logins()
    bad = [n for n in ["BUFFER_API_KEY", *[f"BUFFER_API_KEY_{l.upper()}" for l in logins if l != "default"]]
           if (c := last_check(n)) and not c["ok"]]
    step("buffer_account", bool(logins) and not bad,
         (f"last live check FAILED for {bad}" if bad else f"Buffer logins: {sorted(logins)}") if logins else "no Buffer key",
         "Ask whether the owner already has Buffer with channels connected. If not, walk docs/buffer-setup.md §1–4 "
         "with them one step at a time. Then run `uv run sma setup keys --only BUFFER_API_KEY` (opens a local form).")
    if logins and live:
        for l in logins:
            v = validate("BUFFER_API_KEY" if l == "default" else f"BUFFER_API_KEY_{l.upper()}")
            step(f"buffer_live[{l}]", v["ok"] and not v["detail"].startswith("0 channels"), v["detail"],
                 "Key rejected or no channels: re-create the key (docs/buffer-setup.md §5) or connect channels (§3).")
    gem = bool(config.secret("GEMINI_API_KEY") or config.secret("GOOGLE_API_KEY"))
    gc = last_check("GEMINI_API_KEY")
    step("gemini_key", gem and not (gc and not gc["ok"]),
         ("Gemini key set" + (" (verified)" if gc else " (not verified yet — run status --live)")) if gem and not (gc and not gc["ok"])
         else ("last live check FAILED: " + gc["detail"][:80]) if gem else "no Gemini key",
         "Run `uv run sma setup keys --only GEMINI_API_KEY` (key from https://aistudio.google.com/apikey).")
    if gem and live:
        try:
            g = gemini_models()
            step("gemini_model", g["configured_available"], f"{g['configured']} available={g['configured_available']}; suggested {g['suggested']}",
                 "Run `uv run sma setup gemini --fix --test`.")
        except Exception as e:
            step("gemini_model", False, config.redact(str(e))[:200], "Check the key: `uv run sma setup keys --only GEMINI_API_KEY`.")
    mcp_ok = all((config.ROOT / d / "config.toml").exists() for d in (".codex", ".grok"))
    step("mcp_configs", mcp_ok, "Codex/Grok MCP configs generated" if mcp_ok else "not generated",
         "Run `python3 scripts/sync_mcp.py`.", required=False)

    accounts = config.list_accounts()
    step("first_account", bool(accounts), f"accounts: {accounts}" if accounts else "no accounts yet",
         "Ask the owner which account to set up first, then run the `onboard-account` skill.")
    db = store.connect() if accounts else None
    for s in accounts:
        a = config.load_account(s)
        n = db.execute("SELECT count(*) FROM posts WHERE account=?", (s,)).fetchone()[0]
        last = db.execute("SELECT max(captured_on) FROM post_metrics pm JOIN posts p ON p.id=pm.post_id WHERE p.account=?", (s,)).fetchone()[0]
        step(f"account[{s}].channels", a.get("channels"), f"{len(a.get('channels') or [])} Buffer channels linked",
             f"`uv run sma buffer channels`, then `uv run sma buffer link {s} --channel <id>`.")
        step(f"account[{s}].synced", n > 0, f"{n} posts in store, last metrics snapshot {last}", f"`uv run sma sync {s} --days 365`.")
        step(f"account[{s}].onboarded", a.get("status") == "active", f"status={a.get('status')}",
             f"Run the `onboard-account` skill for {s}.")
        services = {p.get("service") for p in a.get("platforms", [])}
        conns = a.get("connectors") or {}
        offered: set[str] = set()
        for svc, key, cmd in (("youtube", "youtube", "youtube"), ("instagram", "instagram", "instagram"),
                              ("threads", "threads", "threads"), ("twitter", "x", "x"), ("x", "x", "x"),
                              ("linkedin", "linkedin", "linkedin")):
            if svc in services and key not in offered:
                offered.add(key)
                ok = any(k == key or k.startswith(key + "_") for k in conns)
                step(f"account[{s}].{key}_insights", ok, "connected" if ok else "not connected (optional depth)",
                     f"Offer deeper {key} analytics: docs/connect-{cmd}.md, then `uv run sma connect {cmd} {s}`.", required=False)
        if "tiktok" in services:
            has = db.execute("SELECT count(*) FROM posts WHERE account=? AND service='tiktok' AND id LIKE 'tiktok:%'", (s,)).fetchone()[0]
            step(f"account[{s}].tiktok_export", has > 0, f"{has} videos imported from TikTok Studio",
                 f"Offer TikTok Studio export import: docs/connect-tiktok.md, then `uv run sma import tiktok {s} <file>`.", required=False)
    step("daily_sync", schedule_installed(), "scheduled" if schedule_installed() else "not scheduled",
         "Ask the owner, then `uv run sma setup schedule --at 06:30`.", required=False)

    req = [s for s in steps if s["required"] and not s["ok"]]
    opt = [s for s in steps if not s["required"] and not s["ok"]]
    return {"complete": not req, "next_step": (req or opt or [None])[0], "pending_required": len(req),
            "pending_optional": len(opt), "steps": steps}


def brief(st: dict) -> str:
    lines = ["[social-analyst setup status]"]
    if st["complete"] and not st["pending_optional"]:
        lines.append("Setup complete. Accounts: " + ", ".join(config.list_accounts()) + ". Read AGENTS.md, then ask the owner what they want to do.")
    else:
        lines.append(f"{'Required setup is complete' if st['complete'] else str(st['pending_required']) + ' required setup step(s) pending'}; "
                     f"{st['pending_optional']} optional.")
        for s in st["steps"]:
            mark = "✓" if s["ok"] else ("✗" if s["required"] else "○")
            lines.append(f"  {mark} {s['id']}: {s['detail']}")
        n = st["next_step"]
        lines.append(f"NEXT: {n['id']} → {n.get('next')}")
        lines.append("Use the `setup` skill (.agents/skills/setup/SKILL.md) to drive this with the owner. "
                     "Greet them, say in one line what's missing, and offer to start.")
    return "\n".join(lines)


def init() -> dict:
    done = []
    if not config.ENV_FILE.exists():
        config.write_private(config.ENV_FILE, (config.ROOT / ".env.example").read_text())
        done.append("created .env from .env.example")
    for d in (config.DATA, config.MEDIA, config.TOKENS):
        d.mkdir(parents=True, exist_ok=True)
    os.chmod(config.TOKENS, 0o700)
    subprocess.run([sys.executable, str(config.ROOT / "scripts/sync_mcp.py")], check=False, capture_output=True)
    done.append("generated .codex/config.toml and .grok/config.toml")
    return {"done": done}
