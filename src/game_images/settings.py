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
_KEY_OPENAI_AUTH_MODE = "openai_auth_mode"
OpenAiAuthMode = str  # "auto" | "api_key" | "oauth"
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


def get_openai_auth_mode() -> str:
    """How to choose between API key and OAuth when both are available."""
    mode = (_load_raw().get(_KEY_OPENAI_AUTH_MODE) or "auto").strip().lower()
    if mode not in ("auto", "api_key", "oauth"):
        return "auto"
    return mode


def set_openai_auth_mode(mode: str) -> str:
    normalized = (mode or "auto").strip().lower()
    if normalized not in ("auto", "api_key", "oauth"):
        raise ValueError("openai_auth_mode must be auto, api_key, or oauth")
    data = _load_raw()
    data[_KEY_OPENAI_AUTH_MODE] = normalized
    _save_raw(data)
    return normalized


def _env_openai_oauth_token() -> str | None:
    for env_name in ("OPENAI_OAUTH_TOKEN", "OPENAI_ACCESS_TOKEN"):
        env = os.environ.get(env_name, "").strip()
        if env:
            return env
    return None


def get_openai_oauth_access_token() -> str | None:
    """Return a valid OAuth access token, refreshing when expired."""
    env = _env_openai_oauth_token()
    if env:
        return env
    return get_stored_openai_oauth_access_token()


def get_stored_openai_oauth_access_token() -> str | None:
    """OAuth from settings/session only (no environment variables)."""
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


def _pick_openai_credential(
    *,
    api_key: str | None,
    oauth: str | None,
    mode: str,
) -> str | None:
    if api_key and not oauth:
        return api_key
    if oauth and not api_key:
        return oauth
    if not api_key and not oauth:
        return None
    if mode == "oauth":
        return oauth
    if mode == "api_key":
        return api_key
    return api_key  # auto: prefer API key


def is_openai_platform_api_key(credential: str) -> bool:
    """True for platform.openai.com API keys (sk-…), not ChatGPT OAuth JWTs."""
    return (credential or "").strip().startswith("sk-")


OPENAI_IMAGES_NEED_API_KEY_MSG = (
    "OpenAI image generation (Create, Extend, Manipulate) requires a platform API key "
    "from https://platform.openai.com/api-keys. ChatGPT sign-in (OAuth) does not grant "
    "the Images API scope (api.model.images.request), even though images work on "
    "chatgpt.com. In Settings, set \"Use for OpenAI requests\" to API key only and save "
    "your key."
)

OPENAI_IMAGES_API_OAUTH_NOTE = (
    "Create, Extend, and Manipulate need a platform API key (sk-…), not ChatGPT "
    "sign-in. OAuth tokens lack api.model.images.request; chatgpt.com uses a different "
    "service."
)


def validate_openai_images_credential(credential: str | None = None) -> str:
    """Return a credential suitable for the OpenAI Images API or raise ValueError."""
    cred = (credential if credential is not None else get_openai_credential()) or ""
    cred = cred.strip()
    if not cred:
        raise ValueError(
            "OpenAI credentials not set. Add a platform API key in Settings "
            "(https://platform.openai.com/api-keys) or set OPENAI_API_KEY."
        )
    if not is_openai_platform_api_key(cred):
        raise ValueError(OPENAI_IMAGES_NEED_API_KEY_MSG)
    return cred


def get_openai_credential() -> str | None:
    """OpenAI API key or OAuth access token, respecting auth mode preference."""
    mode = get_openai_auth_mode()
    env_key = os.environ.get("OPENAI_API_KEY", "").strip() or None
    env_oauth = _env_openai_oauth_token()
    if env_key or env_oauth:
        picked = _pick_openai_credential(api_key=env_key, oauth=env_oauth, mode=mode)
        if picked:
            return picked
    stored_key = (_load_raw().get(_KEY_OPENAI) or "").strip() or None
    stored_oauth = get_stored_openai_oauth_access_token()
    return _pick_openai_credential(api_key=stored_key, oauth=stored_oauth, mode=mode)


def get_openai_api_key() -> str | None:
    """Backward-compatible alias for OpenAI auth used by providers."""
    return get_openai_credential()


def openai_active_auth() -> str | None:
    """Which credential OpenAI requests use (matches get_openai_credential)."""
    cred = get_openai_credential()
    if not cred:
        return None
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    env_oauth = _env_openai_oauth_token()
    if env_key and cred == env_key:
        return "api_key_env"
    if env_oauth and cred == env_oauth:
        return "oauth_env"
    stored_key = (_load_raw().get(_KEY_OPENAI) or "").strip()
    if stored_key and cred == stored_key:
        return "api_key_stored"
    if get_openai_oauth_session():
        return "oauth_session"
    if (_load_raw().get(_KEY_OPENAI_OAUTH) or "").strip():
        return "oauth_stored"
    if get_stored_openai_oauth_access_token() and cred == get_stored_openai_oauth_access_token():
        return "oauth_session"
    return "oauth_session" if get_openai_oauth_session() else "oauth_stored"


def openai_auth_status() -> dict[str, Any]:
    """How OpenAI auth is configured (for settings UI; never returns raw secrets)."""
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    env_oauth = _env_openai_oauth_token() or ""
    raw = _load_raw()
    stored_key = (raw.get(_KEY_OPENAI) or "").strip()
    stored_oauth = (raw.get(_KEY_OPENAI_OAUTH) or "").strip()
    session = get_openai_oauth_session()
    oauth_via_session = bool(session and session.get("access_token"))
    mode = get_openai_auth_mode()
    base: dict[str, Any] = {
        "auth_mode": mode,
        "api_key_stored": bool(stored_key),
        "api_key_hint": mask_secret(stored_key),
        "oauth_stored": oauth_via_session or bool(stored_oauth),
        "oauth_hint": mask_secret(
            (session or {}).get("access_token", "") or stored_oauth
        ),
        "oauth_session": oauth_via_session,
        "oauth_account_id": (session or {}).get("account_id"),
        "has_api_key": bool(env_key or stored_key),
        "has_oauth": bool(env_oauth or oauth_via_session or stored_oauth),
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


_AUTH_MODE_LABELS = {
    "auto": "Automatic (prefer API key when both are set)",
    "api_key": "Always use API key",
    "oauth": "Always use OAuth",
}


def enrich_openai_auth_status(status: dict[str, Any]) -> dict[str, Any]:
    active = openai_active_auth()
    out = dict(status)
    out["active_auth"] = active
    out["active_auth_label"] = _ACTIVE_AUTH_LABELS.get(active, "") if active else ""
    mode = out.get("auth_mode", "auto")
    out["auth_mode_label"] = _AUTH_MODE_LABELS.get(mode, mode)
    if active and active.startswith("oauth"):
        out["oauth_supports_images_api"] = False
        out["images_api_note"] = OPENAI_IMAGES_API_OAUTH_NOTE
    elif active and active.startswith("api_key"):
        out["oauth_supports_images_api"] = True
        out["images_api_note"] = ""
    else:
        out["oauth_supports_images_api"] = None
        out["images_api_note"] = ""
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
    openai_auth_mode: str | None = None,
    fal_api_key: str | None = None,
    gemini_api_key: str | None = None,
    minimax_api_key: str | None = None,
) -> dict[str, Any]:
    """Update stored keys. Pass None to leave unchanged, '' to remove stored value."""
    data = _load_raw()
    if openai_auth_mode is not None:
        mode = (openai_auth_mode or "auto").strip().lower()
        if mode not in ("auto", "api_key", "oauth"):
            raise ValueError("openai_auth_mode must be auto, api_key, or oauth")
        data[_KEY_OPENAI_AUTH_MODE] = mode
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
