"""Shared OAuth 2.0 authorization-code helper (loopback redirect, optional PKCE) + token files.

Used by the X and LinkedIn connectors. The redirect URI must be registered in the platform's app
settings exactly: http://localhost:<port>/callback (default port 8765, `SMA_OAUTH_PORT` to change).
Tokens live in data/tokens/<service>__<slug>.json with 0600 permissions.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .. import config, store


def port() -> int:
    return int(config.env("SMA_OAUTH_PORT", "8765"))


def redirect_uri() -> str:
    return f"http://localhost:{port()}/callback"


def token_path(service: str, slug: str):
    return config.TOKENS / f"{service}__{slug}.json"


def load_token(service: str, slug: str) -> dict:
    p = token_path(service, slug)
    if not p.exists():
        raise SystemExit(f"{service} not connected for {slug}: `uv run sma connect {service} {slug}`")
    tok = json.loads(p.read_text())
    for k in ("access_token", "refresh_token"):
        if tok.get(k):
            config._SECRETS.add(tok[k])
    return tok


def save_token(service: str, slug: str, tok: dict) -> None:
    if "expires_in" in tok and "expires_at" not in tok:
        tok["expires_at"] = int(time.time()) + int(tok["expires_in"])
    tok["saved_at"] = store.now()
    config.write_private(token_path(service, slug), json.dumps(tok, indent=2))


def authorize(*, auth_url: str, token_url: str, client_id: str, client_secret: str | None, scopes: list[str],
              pkce: bool, extra_auth: dict | None = None, basic_auth: bool = False, timeout: int = 600) -> dict:
    """Run the browser consent; return the token response JSON."""
    state = secrets.token_urlsafe(16)
    params = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri(),
              "scope": " ".join(scopes), "state": state, **(extra_auth or {})}
    verifier = None
    if pkce:
        verifier = secrets.token_urlsafe(64)[:96]
        params["code_challenge"] = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        params["code_challenge_method"] = "S256"
    url = f"{auth_url}?{urlencode(params)}"
    got: dict = {}
    done = threading.Event()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            if urlparse(self.path).path != "/callback":
                self.send_response(404); self.end_headers(); return
            got.update({k: v[0] for k, v in q.items()})
            ok = got.get("state") == state and "code" in got
            self.send_response(200); self.send_header("content-type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write((b"<h2>Connected.</h2><p>You can close this tab and return to your agent.</p>" if ok else
                              f"<h2>Not connected</h2><p>{got.get('error_description') or got.get('error') or 'state mismatch'}</p>".encode()))
            done.set()

    srv = HTTPServer(("127.0.0.1", port()), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(json.dumps({"authorize_url": url, "redirect_uri": redirect_uri(), "waiting_seconds": timeout}), flush=True)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    finished = done.wait(timeout)
    srv.shutdown()
    if not finished:
        raise SystemExit("timed out waiting for the browser consent; run the connect command again")
    if got.get("state") != state or "code" not in got:
        raise SystemExit(f"authorization failed: {got.get('error_description') or got.get('error') or 'state mismatch'}")
    data = {"grant_type": "authorization_code", "code": got["code"], "redirect_uri": redirect_uri(), "client_id": client_id}
    if verifier:
        data["code_verifier"] = verifier
    auth = None
    if client_secret:
        if basic_auth:
            auth = (client_id, client_secret)
        else:
            data["client_secret"] = client_secret
    r = httpx.post(token_url, data=data, auth=auth, timeout=60)
    if r.status_code >= 400:
        raise SystemExit(config.redact(f"token exchange failed {r.status_code}: {r.text[:300]}"))
    return r.json()


def refresh(*, token_url: str, tok: dict, client_id: str, client_secret: str | None, basic_auth: bool = False) -> dict | None:
    if not tok.get("refresh_token"):
        return None
    data = {"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": client_id}
    auth = None
    if client_secret:
        if basic_auth:
            auth = (client_id, client_secret)
        else:
            data["client_secret"] = client_secret
    r = httpx.post(token_url, data=data, auth=auth, timeout=60)
    if r.status_code >= 400:
        return None
    new = r.json()
    new.setdefault("refresh_token", tok["refresh_token"])
    new.pop("expires_at", None)
    return new


def expiring(tok: dict, within_s: int = 300) -> bool:
    return bool(tok.get("expires_at")) and tok["expires_at"] - time.time() < within_s
