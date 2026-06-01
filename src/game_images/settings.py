"""Local settings storage (API keys) for the web UI."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from game_images.library import get_library_path

_SETTINGS_FILENAME = "settings.json"
_KEY_OPENAI = "openai_api_key"
_KEY_OPENAI_OAUTH = "openai_oauth_token"
_KEY_OPENAI_OAUTH_SESSION = "openai_oauth_session"
_KEY_FAL = "fal_api_key"
_KEY_GEMINI = "gemini_api_key"
_KEY_MINIMAX = "minimax_api_key"


def _settings_path() -> Path:
    return get_library_path() / _SETTINGS_FILENAME


def _load_raw() -> dict[str, Any]:
    path = _settings_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_raw(data: dict[str, Any]) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def mask_secret(value: str) -> str:
    """Return a short masked hint for display (never the full key)."""
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= 8:
        return "••••••••"
    return v[:4] + "…" + v[-4:]


def get_openai_oauth_session() -> dict[str, Any] | None:
    raw = _load_raw().get(_KEY_OPENAI_OAUTH_SESSION)
    return raw if isinstance(raw, dict) and raw.get("access_token") else None


def save_openai_oauth_session(tokens: dict[str, Any]) -> None:
    data = _load_raw()
    data[_KEY_OPENAI_OAUTH_SESSION] = {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "expires_at": tokens.get("expires_at"),
        "account_id": tokens.get("account_id"),
    }
    data.pop(_KEY_OPENAI_OAUTH, None)
    _save_raw(data)


def clear_openai_oauth_session() -> None:
    data = _load_raw()
    data.pop(_KEY_OPENAI_OAUTH_SESSION, None)
    data.pop(_KEY_OPENAI_OAUTH, None)
    _save_raw(data)


def get_openai_oauth_access_token() -> str | None:
    """Return a valid OAuth access token, refreshing when expired."""
    for env_name in ("OPENAI_OAUTH_TOKEN", "OPENAI_ACCESS_TOKEN"):
        env = os.environ.get(env_name, "").strip()
        if env:
            return env
    session = get_openai_oauth_session()
    if not session:
        legacy = (_load_raw().get(_KEY_OPENAI_OAUTH) or "").strip()
        return legacy or None
    access = (session.get("access_token") or "").strip()
    refresh = (session.get("refresh_token") or "").strip()
    expires_at = session.get("expires_at") or 0
    if not access or not refresh:
        return None
    if int(expires_at) > int(time.time()) + 60:
        return access
    from game_images.openai_codex_oauth import refresh_tokens

    try:
        updated = refresh_tokens(refresh)
        save_openai_oauth_session(updated)
        return updated.get("access_token")
    except Exception:
        return access if int(expires_at) > int(time.time()) else None


def get_openai_credential() -> str | None:
    """OpenAI API key or OAuth access token. Env vars win over stored settings."""
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key
    stored_key = (_load_raw().get(_KEY_OPENAI) or "").strip()
    if stored_key:
        return stored_key
    oauth = get_openai_oauth_access_token()
    if oauth:
        return oauth
    return None


def get_openai_api_key() -> str | None:
    """Backward-compatible alias for OpenAI auth used by providers."""
    return get_openai_credential()


def openai_active_auth() -> str | None:
    """Which credential OpenAI requests use (matches get_openai_credential precedence)."""
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return "api_key_env"
    if (_load_raw().get(_KEY_OPENAI) or "").strip():
        return "api_key_stored"
    if os.environ.get("OPENAI_OAUTH_TOKEN", "").strip() or os.environ.get(
        "OPENAI_ACCESS_TOKEN", ""
    ).strip():
        return "oauth_env"
    if get_openai_oauth_session():
        return "oauth_session"
    if (_load_raw().get(_KEY_OPENAI_OAUTH) or "").strip():
        return "oauth_stored"
    return None


def openai_auth_status() -> dict[str, Any]:
    """How OpenAI auth is configured (for settings UI; never returns raw secrets)."""
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    env_oauth = (
        os.environ.get("OPENAI_OAUTH_TOKEN", "").strip()
        or os.environ.get("OPENAI_ACCESS_TOKEN", "").strip()
    )
    raw = _load_raw()
    stored_key = (raw.get(_KEY_OPENAI) or "").strip()
    stored_oauth = (raw.get(_KEY_OPENAI_OAUTH) or "").strip()
    session = get_openai_oauth_session()
    oauth_via_session = bool(session and session.get("access_token"))
    base: dict[str, Any] = {
        "api_key_stored": bool(stored_key),
        "api_key_hint": mask_secret(stored_key),
        "oauth_stored": oauth_via_session or bool(stored_oauth),
        "oauth_hint": mask_secret(
            (session or {}).get("access_token", "") or stored_oauth
        ),
        "oauth_session": oauth_via_session,
        "oauth_account_id": (session or {}).get("account_id"),
    }
    if env_key:
        return {
            **base,
            "set": True,
            "from_env": True,
            "auth_method": "api_key",
            "hint": mask_secret(env_key),
        }
    if env_oauth:
        return {
            **base,
            "set": True,
            "from_env": True,
            "auth_method": "oauth",
            "hint": mask_secret(env_oauth),
        }
    if stored_key:
        return {
            **base,
            "set": True,
            "from_env": False,
            "auth_method": "api_key",
            "hint": mask_secret(stored_key),
        }
    if stored_oauth:
        return {
            **base,
            "set": True,
            "from_env": False,
            "auth_method": "oauth",
            "hint": mask_secret(stored_oauth),
        }
    if oauth_via_session:
        return {
            **base,
            "set": True,
            "from_env": False,
            "auth_method": "oauth",
            "hint": mask_secret((session or {}).get("access_token", "")),
        }
    return {
        **base,
        "set": False,
        "from_env": False,
        "auth_method": None,
        "hint": "",
    }


_ACTIVE_AUTH_LABELS = {
    "api_key_env": "API key (OPENAI_API_KEY environment variable)",
    "api_key_stored": "API key (saved in Settings)",
    "oauth_env": "OAuth token (OPENAI_OAUTH_TOKEN / OPENAI_ACCESS_TOKEN environment variable)",
    "oauth_session": "OAuth (Sign in with OpenAI session)",
    "oauth_stored": "OAuth token (saved manually in Settings)",
}


def enrich_openai_auth_status(status: dict[str, Any]) -> dict[str, Any]:
    active = openai_active_auth()
    out = dict(status)
    out["active_auth"] = active
    out["active_auth_label"] = _ACTIVE_AUTH_LABELS.get(active, "") if active else ""
    return out


def get_fal_api_key() -> str | None:
    env = os.environ.get("FAL_KEY", "").strip()
    if env:
        return env
    stored = (_load_raw().get(_KEY_FAL) or "").strip()
    return stored or None


def get_gemini_api_key() -> str | None:
    for env_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        env = os.environ.get(env_name, "").strip()
        if env:
            return env
    stored = (_load_raw().get(_KEY_GEMINI) or "").strip()
    return stored or None


def get_minimax_api_key() -> str | None:
    env = os.environ.get("MINIMAX_API_KEY", "").strip()
    if env:
        return env
    stored = (_load_raw().get(_KEY_MINIMAX) or "").strip()
    return stored or None


def keys_status() -> dict[str, Any]:
    """Public key status for the UI (masked, no raw secrets)."""
    raw = _load_raw()
    fal_stored = (raw.get(_KEY_FAL) or "").strip()
    gemini_stored = (raw.get(_KEY_GEMINI) or "").strip()
    minimax_stored = (raw.get(_KEY_MINIMAX) or "").strip()
    fal_env = bool(os.environ.get("FAL_KEY", "").strip())
    gemini_env = bool(
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
    )
    minimax_env = bool(os.environ.get("MINIMAX_API_KEY", "").strip())
    return {
        "openai": enrich_openai_auth_status(openai_auth_status()),
        "fal": {
            "set": bool(fal_stored or fal_env),
            "from_env": fal_env,
            "hint": mask_secret(os.environ.get("FAL_KEY", "") or fal_stored),
        },
        "gemini": {
            "set": bool(gemini_stored or gemini_env),
            "from_env": gemini_env,
            "hint": mask_secret(
                os.environ.get("GEMINI_API_KEY", "")
                or os.environ.get("GOOGLE_API_KEY", "")
                or gemini_stored
            ),
        },
        "minimax": {
            "set": bool(minimax_stored or minimax_env),
            "from_env": minimax_env,
            "hint": mask_secret(
                os.environ.get("MINIMAX_API_KEY", "") or minimax_stored
            ),
        },
        "settings_path": str(_settings_path()),
    }


def update_keys(
    *,
    openai_api_key: str | None = None,
    openai_oauth_token: str | None = None,
    fal_api_key: str | None = None,
    gemini_api_key: str | None = None,
    minimax_api_key: str | None = None,
) -> dict[str, Any]:
    """Update stored keys. Pass None to leave unchanged, '' to remove stored value."""
    data = _load_raw()
    if openai_api_key is not None:
        if openai_api_key.strip():
            data[_KEY_OPENAI] = openai_api_key.strip()
        else:
            data.pop(_KEY_OPENAI, None)
    if openai_oauth_token is not None:
        if openai_oauth_token.strip():
            data[_KEY_OPENAI_OAUTH] = openai_oauth_token.strip()
            data.pop(_KEY_OPENAI_OAUTH_SESSION, None)
        else:
            data.pop(_KEY_OPENAI_OAUTH, None)
            data.pop(_KEY_OPENAI_OAUTH_SESSION, None)
    if fal_api_key is not None:
        if fal_api_key.strip():
            data[_KEY_FAL] = fal_api_key.strip()
        else:
            data.pop(_KEY_FAL, None)
    if gemini_api_key is not None:
        if gemini_api_key.strip():
            data[_KEY_GEMINI] = gemini_api_key.strip()
        else:
            data.pop(_KEY_GEMINI, None)
    if minimax_api_key is not None:
        if minimax_api_key.strip():
            data[_KEY_MINIMAX] = minimax_api_key.strip()
        else:
            data.pop(_KEY_MINIMAX, None)
    _save_raw(data)
    return keys_status()
