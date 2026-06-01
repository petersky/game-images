"""OpenAI ChatGPT/Codex OAuth (PKCE) for local sign-in without pasting tokens."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable

# Public client id used by Codex CLI and compatible local tools (see openai-codex provider).
CLIENT_ID = os.environ.get("OPENAI_OAUTH_CLIENT_ID", "app_EMoamEEZ73f0CkXaXp7hrann")
AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
SCOPE = "openid profile email offline_access"
JWT_CLAIM_PATH = "https://api.openai.com/auth"
ORIGINATOR = os.environ.get("GAME_IMAGES_OPENAI_ORIGINATOR", "game-images")

# OpenAI registers this redirect for the Codex CLI client.
CODEX_REDIRECT_URI = "http://localhost:1455/auth/callback"

_pending: dict[str, dict[str, Any]] = {}
_pending_lock = threading.Lock()
_callback_server: HTTPServer | None = None
_callback_thread: threading.Thread | None = None
_callback_handler: Callable[[str, str], tuple[int, str]] | None = None

SUCCESS_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Signed in</title>
<style>body{font-family:system-ui,sans-serif;background:#1a1b26;color:#c0caf5;padding:2rem;text-align:center}
.ok{color:#9ece6a}</style></head>
<body><h1 class="ok">OpenAI sign-in complete</h1>
<p>You can close this tab and return to Game Images.</p>
<script>try{if(window.opener){window.opener.postMessage({type:'game-images-openai-oauth',status:'success'},'*');}}catch(e){}</script>
</body></html>"""

ERROR_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>Sign-in failed</title>
<style>body{font-family:system-ui,sans-serif;background:#1a1b26;color:#c0caf5;padding:2rem}
.err{color:#f7768e}</style></head>
<body><h1 class="err">OpenAI sign-in failed</h1>
<p>{message}</p>
<script>try{if(window.opener){window.opener.postMessage({type:'game-images-openai-oauth',status:'error',message:{message}},'*');}}catch(e){}</script>
</body></html>"""


def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        padding = "=" * (-len(payload) % 4)
        raw = base64.urlsafe_b64decode(payload + padding)
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, ValueError):
        return None


def account_id_from_access_token(access_token: str) -> str | None:
    payload = _decode_jwt_payload(access_token)
    if not payload:
        return None
    auth = payload.get(JWT_CLAIM_PATH)
    if isinstance(auth, dict):
        aid = auth.get("chatgpt_account_id")
        if isinstance(aid, str) and aid:
            return aid
    return None


def default_redirect_uri(port: int = 8000) -> str:
    custom = os.environ.get("GAME_IMAGES_OPENAI_REDIRECT_URI", "").strip()
    if custom:
        return custom
    if os.environ.get("GAME_IMAGES_OPENAI_USE_APP_REDIRECT", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return f"http://127.0.0.1:{port}/auth/openai/callback"
    return CODEX_REDIRECT_URI


def build_authorization_url(
    *,
    redirect_uri: str,
    state: str,
    verifier: str,
    originator: str = ORIGINATOR,
) -> str:
    _challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": SCOPE,
        "code_challenge": _challenge,
        "code_challenge_method": "S256",
        "state": state,
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
        "originator": originator,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def _token_request(body: dict[str, str]) -> dict[str, Any]:
    data = urllib.parse.urlencode(body).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI token request failed ({e.code}): {detail}") from e


def exchange_code(code: str, verifier: str, redirect_uri: str) -> dict[str, Any]:
    payload = _token_request(
        {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        }
    )
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    if not access or not refresh or not isinstance(expires_in, (int, float)):
        raise RuntimeError("OpenAI token response missing required fields")
    expires_at = int(time.time()) + int(expires_in)
    account_id = account_id_from_access_token(str(access))
    return {
        "access_token": str(access),
        "refresh_token": str(refresh),
        "expires_at": expires_at,
        "account_id": account_id,
    }


def refresh_tokens(refresh_token: str) -> dict[str, Any]:
    payload = _token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        }
    )
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    if not access or not refresh or not isinstance(expires_in, (int, float)):
        raise RuntimeError("OpenAI refresh response missing required fields")
    expires_at = int(time.time()) + int(expires_in)
    return {
        "access_token": str(access),
        "refresh_token": str(refresh),
        "expires_at": expires_at,
        "account_id": account_id_from_access_token(str(access)),
    }


def start_login(*, redirect_port: int = 8000) -> dict[str, str]:
    """Begin OAuth; returns authorization URL and opaque state for polling."""
    redirect_uri = default_redirect_uri(redirect_port)
    state = secrets.token_hex(16)
    verifier, _ = _pkce_pair()
    with _pending_lock:
        _purge_expired_pending()
        _pending[state] = {
            "verifier": verifier,
            "redirect_uri": redirect_uri,
            "created_at": time.time(),
            "status": "pending",
        }
    if redirect_uri.rstrip("/") == CODEX_REDIRECT_URI.rstrip("/"):
        _ensure_codex_callback_server()
    return {
        "auth_url": build_authorization_url(
            redirect_uri=redirect_uri, state=state, verifier=verifier
        ),
        "state": state,
        "redirect_uri": redirect_uri,
    }


def poll_login(state: str) -> dict[str, Any]:
    with _pending_lock:
        entry = _pending.get(state)
        if not entry:
            return {"status": "unknown"}
        return {
            "status": entry.get("status", "pending"),
            "error": entry.get("error"),
        }


def complete_login(state: str, code: str) -> dict[str, Any]:
    with _pending_lock:
        entry = _pending.get(state)
        if not entry:
            raise ValueError("OAuth session expired or unknown. Start sign-in again.")
        if entry.get("status") == "complete":
            return entry.get("tokens") or {}
        verifier = entry["verifier"]
        redirect_uri = entry["redirect_uri"]
    tokens = exchange_code(code, verifier, redirect_uri)
    with _pending_lock:
        if state in _pending:
            _pending[state]["status"] = "complete"
            _pending[state]["tokens"] = tokens
            _pending[state]["error"] = None
    return tokens


def fail_login(state: str, message: str) -> None:
    with _pending_lock:
        if state in _pending:
            _pending[state]["status"] = "error"
            _pending[state]["error"] = message


def _purge_expired_pending(max_age_s: int = 600) -> None:
    now = time.time()
    expired = [s for s, e in _pending.items() if now - e.get("created_at", 0) > max_age_s]
    for s in expired:
        _pending.pop(s, None)


def _ensure_codex_callback_server() -> None:
    global _callback_server, _callback_thread, _callback_handler

    def handler(state: str, code: str) -> tuple[int, str]:
        try:
            with _pending_lock:
                entry = _pending.get(state)
                if not entry:
                    return 400, ERROR_HTML.format(message="Session expired. Try again from Settings.")
                if entry.get("redirect_uri", "").rstrip("/") != CODEX_REDIRECT_URI.rstrip("/"):
                    return 400, ERROR_HTML.format(message="Redirect mismatch.")
            from game_images.settings import save_openai_oauth_session

            tokens = complete_login(state, code)
            save_openai_oauth_session(tokens)
            return 200, SUCCESS_HTML
        except Exception as e:
            fail_login(state, str(e))
            return 500, ERROR_HTML.format(message=str(e).replace("<", "&lt;"))

    _callback_handler = handler
    if _callback_server is not None:
        return

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/auth/callback":
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")
                return
            qs = urllib.parse.parse_qs(parsed.query)
            state = (qs.get("state") or [""])[0]
            code = (qs.get("code") or [""])[0]
            if not state or not code:
                body = ERROR_HTML.format(message="Missing code or state").encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(body)
                return
            assert _callback_handler is not None
            status, html = _callback_handler(state, code)
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = HTTPServer(("127.0.0.1", 1455), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _callback_server = server
    _callback_thread = thread
