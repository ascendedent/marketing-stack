"""Paths, env loading, and secret redaction. Nothing here ever prints a key."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(os.environ.get("SMA_ROOT", Path(__file__).resolve().parents[2]))
ACCOUNTS = ROOT / "accounts"
DATA = ROOT / "data"
DB_PATH = DATA / "sma.db"
MEDIA = DATA / "media"

# Model ids live in env so a deprecation is a .env edit, not a code change.
DEFAULTS = {
    "GEMINI_VIDEO_MODEL": "gemini-3.8-flash",
    "GEMINI_VIDEO_FPS": "2",
    "GEMINI_MEDIA_RESOLUTION": "MEDIA_RESOLUTION_HIGH",
    "SMA_TIMEZONE": "UTC",
}

_SECRETS: set[str] = set()


def _load() -> dict[str, str]:
    """Process env wins; then ./.env; then any files listed in SMA_ENV_FILES (colon-separated)."""
    merged: dict[str, str] = {}
    extra = os.environ.get("SMA_ENV_FILES") or dotenv_values(ROOT / ".env").get("SMA_ENV_FILES") or ""
    for f in [p for p in extra.split(":") if p][::-1]:
        merged.update({k: v for k, v in dotenv_values(os.path.expanduser(f)).items() if v})
    merged.update({k: v for k, v in dotenv_values(ROOT / ".env").items() if v})
    merged.update(os.environ)
    return merged


_ENV = _load()


def env(name: str, default: str | None = None) -> str | None:
    v = _ENV.get(name) or DEFAULTS.get(name) or default
    return v.strip() if isinstance(v, str) else v


def secret(name: str) -> str | None:
    """Read a secret. `NAME_FILE` pointing at a file (raw key or one NAME=key line) also works."""
    v = env(name)
    if not v:
        path = env(f"{name}_FILE")
        if path:
            try:
                raw = Path(os.path.expanduser(path)).read_text()
            except OSError as e:
                raise RuntimeError(f"{name}_FILE is set but unreadable ({path})") from e
            line = next((l.strip() for l in raw.splitlines() if l.strip() and not l.startswith("#")), "")
            m = re.match(r"^[A-Za-z_][A-Za-z0-9_]*=(.*)$", line)
            v = (m.group(1) if m else line).strip().strip("'\"")
    if v and len(v) >= 8:
        _SECRETS.add(v)
    return v or None


def redact(text: str) -> str:
    for s in _SECRETS:
        text = text.replace(s, "[redacted]")
    return text


# ---- Buffer keys -----------------------------------------------------------
# One Buffer login per key. `BUFFER_API_KEY` is the "default" login; any
# `BUFFER_API_KEY_<NAME>` adds another login called <name> (e.g. BUFFER_API_KEY_CLIENTA).
# Each may instead be given as `<VAR>_FILE` pointing at a key file.

def buffer_logins() -> dict[str, str]:
    logins: dict[str, str] = {}
    for name in sorted({k.removesuffix("_FILE") for k in _ENV}):
        if name == "BUFFER_API_KEY":
            label = "default"
        elif name.startswith("BUFFER_API_KEY_"):
            label = name.removeprefix("BUFFER_API_KEY_").lower()
        else:
            continue
        key = secret(name)
        if key and label not in logins:
            logins[label] = key
    return logins


def account_dir(slug: str) -> Path:
    d = ACCOUNTS / slug
    if not d.exists():
        raise SystemExit(f"no account '{slug}' — run `sma account new {slug}` (see accounts/_template)")
    return d


def load_account(slug: str) -> dict:
    return json.loads((account_dir(slug) / "account.json").read_text())


def list_accounts() -> list[str]:
    return sorted(p.name for p in ACCOUNTS.iterdir() if p.is_dir() and not p.name.startswith("_"))


TOKENS = DATA / "tokens"
ENV_FILE = ROOT / ".env"


def save_account(slug: str, acct: dict) -> None:
    (account_dir(slug) / "account.json").write_text(json.dumps(acct, indent=2))


def write_private(path: Path, text: str) -> None:
    """Write a token/secret file readable only by the owner."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def set_env_value(name: str, value: str) -> None:
    """Create/replace NAME=value in .env (from .env.example if .env doesn't exist). Never echoes."""
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
        raise ValueError(f"bad env var name {name!r}")
    if not ENV_FILE.exists():
        example = ROOT / ".env.example"
        write_private(ENV_FILE, example.read_text() if example.exists() else "")
    lines = ENV_FILE.read_text().splitlines()
    pat = re.compile(rf"^\s*#?\s*{name}=")
    out, done = [], False
    for l in lines:
        if pat.match(l) and not done:
            out.append(f"{name}={value}")
            done = True
        elif pat.match(l):
            continue
        else:
            out.append(l)
    if not done:
        out.append(f"{name}={value}")
    write_private(ENV_FILE, "\n".join(out) + "\n")
    _ENV[name] = value
    if len(value) >= 8:
        _SECRETS.add(value)


def reload_env() -> None:
    global _ENV
    _ENV = _load()
