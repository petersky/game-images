"""Tests for OpenAI Codex OAuth helpers."""

import json
from unittest.mock import MagicMock, patch

from game_images.openai_codex_oauth import (
    account_id_from_access_token,
    build_authorization_url,
    exchange_code,
    start_login,
)


def test_build_authorization_url_contains_pkce() -> None:
    verifier = "test_verifier_12345"
    url = build_authorization_url(
        redirect_uri="http://127.0.0.1:8000/auth/openai/callback",
        state="abc",
        verifier=verifier,
    )
    assert "auth.openai.com" in url
    assert "code_challenge=" in url
    assert "state=abc" in url
    assert "originator=game-images" in url or "originator=" in url


def test_exchange_code_parses_tokens() -> None:
    body = json.dumps(
        {
            "access_token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.sig",
            "refresh_token": "refresh-abc",
            "expires_in": 3600,
        }
    ).encode("utf-8")

    def fake_urlopen(req, timeout=60):
        resp = MagicMock()
        resp.read.return_value = body
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    with patch("urllib.request.urlopen", fake_urlopen):
        tokens = exchange_code("code123", "verifier", "http://localhost:1455/auth/callback")
    assert tokens["access_token"].startswith("eyJ")
    assert tokens["refresh_token"] == "refresh-abc"
    assert tokens["expires_at"] > 0


def test_start_login_returns_url_and_state() -> None:
    with patch.dict("os.environ", {"GAME_IMAGES_OPENAI_USE_CODEX_REDIRECT": ""}, clear=False):
        result = start_login(redirect_port=8000)
    assert "auth_url" in result
    assert "state" in result
    assert len(result["state"]) >= 16


def test_account_id_from_jwt() -> None:
    import base64

    payload = {"https://api.openai.com/auth": {"chatgpt_account_id": "acct-99"}}
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    token = f"hdr.{raw}.sig"
    assert account_id_from_access_token(token) == "acct-99"
