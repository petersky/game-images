"""Local settings storage (API keys) for the web UI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from game_images.library import get_library_path

_SETTINGS_FILENAME = "settings.json"
_KEY_OPENAI = "openai_api_key"
_KEY_FAL = "fal_api_key"


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


def get_openai_api_key() -> str | None:
    """Env var wins over stored settings."""
    env = os.environ.get("OPENAI_API_KEY", "").strip()
    if env:
        return env
    stored = (_load_raw().get(_KEY_OPENAI) or "").strip()
    return stored or None


def get_fal_api_key() -> str | None:
    env = os.environ.get("FAL_KEY", "").strip()
    if env:
        return env
    stored = (_load_raw().get(_KEY_FAL) or "").strip()
    return stored or None


def keys_status() -> dict[str, Any]:
    """Public key status for the UI (masked, no raw secrets)."""
    raw = _load_raw()
    openai_stored = (raw.get(_KEY_OPENAI) or "").strip()
    fal_stored = (raw.get(_KEY_FAL) or "").strip()
    openai_env = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    fal_env = bool(os.environ.get("FAL_KEY", "").strip())
    return {
        "openai": {
            "set": bool(openai_stored or openai_env),
            "from_env": openai_env,
            "hint": mask_secret(os.environ.get("OPENAI_API_KEY", "") or openai_stored),
        },
        "fal": {
            "set": bool(fal_stored or fal_env),
            "from_env": fal_env,
            "hint": mask_secret(os.environ.get("FAL_KEY", "") or fal_stored),
        },
        "settings_path": str(_settings_path()),
    }


def update_keys(
    *,
    openai_api_key: str | None = None,
    fal_api_key: str | None = None,
) -> dict[str, Any]:
    """Update stored keys. Pass None to leave unchanged, '' to remove stored value."""
    data = _load_raw()
    if openai_api_key is not None:
        if openai_api_key.strip():
            data[_KEY_OPENAI] = openai_api_key.strip()
        else:
            data.pop(_KEY_OPENAI, None)
    if fal_api_key is not None:
        if fal_api_key.strip():
            data[_KEY_FAL] = fal_api_key.strip()
        else:
            data.pop(_KEY_FAL, None)
    _save_raw(data)
    return keys_status()
