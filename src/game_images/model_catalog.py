"""Discover and cache image models available per provider."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Literal

from game_images.settings import (
    _load_raw,
    _save_raw,
    get_fal_api_key,
    get_gemini_api_key,
    get_minimax_api_key,
    get_openai_api_key,
)

Capability = Literal["create", "extend", "manipulate"]

_CATALOG_KEY = "available_models"

# Known candidates probed or listed when discovery runs
_GEMINI_IMAGE_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("gemini-2.5-flash-image", "Nano Banana (2.5 Flash)"),
    ("gemini-3.1-flash-image-preview", "Nano Banana 2"),
    ("gemini-3.1-flash-image", "Nano Banana 2"),
    ("gemini-3-pro-image-preview", "Nano Banana Pro"),
    ("gemini-3.1-flash-image-preview", "Nano Banana 2 (preview)"),
)

_MINIMAX_IMAGE_MODELS: tuple[tuple[str, str], ...] = (
    ("image-01", "MiniMax Image 01"),
)

_FAL_CREATE_MODELS: tuple[tuple[str, str], ...] = (
    ("flux-schnell", "Fal Flux Schnell"),
)

_DEFAULT_OPENAI_CREATE: tuple[tuple[str, str], ...] = (
    ("gpt-image-1.5", "GPT Image 1.5"),
    ("gpt-image-1", "GPT Image 1"),
    ("gpt-image-1-mini", "GPT Image 1 Mini"),
    ("dall-e-3", "DALL·E 3 (legacy)"),
    ("dall-e-2", "DALL·E 2 (legacy)"),
)

_DEFAULT_OPENAI_EDIT: tuple[tuple[str, str], ...] = (
    ("gpt-image-1.5", "GPT Image 1.5"),
    ("gpt-image-1", "GPT Image 1"),
    ("gpt-image-1-mini", "GPT Image 1 Mini"),
    ("dall-e-2", "DALL·E 2 (legacy)"),
)


def _entry(model_id: str, label: str) -> dict[str, str]:
    return {"id": model_id, "label": label}


def _entries(pairs: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [_entry(mid, lbl) for mid, lbl in pairs]


def default_catalog() -> dict[str, Any]:
    """Static fallback when the user has not run discovery yet."""
    openai_create = _entries(_DEFAULT_OPENAI_CREATE)
    openai_edit = _entries(_DEFAULT_OPENAI_EDIT)
    return {
        "discovered_at": None,
        "providers": {
            "openai": {
                "create": openai_create,
                "extend": openai_edit,
                "manipulate": openai_edit,
            },
            "fal": {
                "create": _entries(_FAL_CREATE_MODELS),
                "extend": [_entry("fal-outpaint", "Fal Outpaint (Gemini)")],
                "manipulate": [_entry("fal-gemini-edit", "Fal Gemini Edit")],
            },
            "gemini": {
                "create": _entries(_GEMINI_IMAGE_CANDIDATES),
                "extend": [],
                "manipulate": [],
            },
            "minimax": {
                "create": _entries(_MINIMAX_IMAGE_MODELS),
                "extend": [],
                "manipulate": [],
            },
        },
    }


def get_catalog() -> dict[str, Any]:
    raw = _load_raw().get(_CATALOG_KEY)
    if not isinstance(raw, dict) or not raw.get("providers"):
        return default_catalog()
    base = default_catalog()
    providers = base["providers"]
    stored = raw.get("providers") or {}
    for pname, caps in stored.items():
        if pname not in providers:
            providers[pname] = {"create": [], "extend": [], "manipulate": []}
        for cap in ("create", "extend", "manipulate"):
            if cap in caps and isinstance(caps[cap], list) and caps[cap]:
                providers[pname][cap] = caps[cap]
    base["discovered_at"] = raw.get("discovered_at")
    return base


def models_for(provider: str, capability: Capability) -> list[dict[str, str]]:
    cat = get_catalog()
    prov = cat.get("providers", {}).get(provider, {})
    models = prov.get(capability) or []
    return list(models) if isinstance(models, list) else []


def save_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    data = _load_raw()
    data[_CATALOG_KEY] = catalog
    _save_raw(data)
    return catalog


def _openai_image_model_ids(api_key: str) -> list[str]:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    ids: list[str] = []
    for m in client.models.list():
        mid = getattr(m, "id", None) or ""
        lower = mid.lower()
        if lower.startswith("gpt-image") or lower.startswith("dall-e"):
            ids.append(mid)
    return sorted(set(ids), key=lambda x: (0 if x.startswith("gpt-image") else 1, x))


def _label_for_openai(model_id: str) -> str:
    if model_id.startswith("gpt-image"):
        return f"GPT Image ({model_id.removeprefix('gpt-image-')})"
    if model_id.startswith("dall-e"):
        return f"DALL·E ({model_id.removeprefix('dall-e-')}) (legacy)"
    return model_id


def discover_openai() -> dict[str, list[dict[str, str]]]:
    key = get_openai_api_key()
    if not key:
        return {}
    try:
        ids = _openai_image_model_ids(key)
    except Exception:
        return {}
    if not ids:
        return {}
    create_ids = [i for i in ids if i.startswith("gpt-image") or i.startswith("dall-e")]
    edit_ids = [i for i in ids if i.startswith("gpt-image") or i == "dall-e-2"]
    return {
        "create": [_entry(i, _label_for_openai(i)) for i in create_ids],
        "extend": [_entry(i, _label_for_openai(i)) for i in edit_ids],
        "manipulate": [_entry(i, _label_for_openai(i)) for i in edit_ids],
    }


def _gemini_list_models(api_key: str) -> list[str]:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models"
        f"?key={urllib.request.quote(api_key, safe='')}"
    )
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    found: list[str] = []
    for item in payload.get("models") or []:
        name = (item.get("name") or "").removeprefix("models/")
        methods = item.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        lower = name.lower()
        if "image" in lower or "imagen" in lower:
            found.append(name)
    return sorted(set(found))


def discover_gemini() -> dict[str, list[dict[str, str]]]:
    key = get_gemini_api_key()
    if not key:
        return {}
    labels = {mid: lbl for mid, lbl in _GEMINI_IMAGE_CANDIDATES}
    try:
        listed = _gemini_list_models(key)
    except Exception:
        listed = []
    if not listed:
        # Key may work but list failed — expose known Nano Banana ids for manual try
        listed = [mid for mid, _ in _GEMINI_IMAGE_CANDIDATES]
    create: list[dict[str, str]] = []
    for mid in listed:
        label = labels.get(mid, f"Gemini ({mid})")
        if "flash-image" in mid and "3.1" in mid:
            label = labels.get(mid, "Nano Banana 2")
        elif "pro-image" in mid:
            label = labels.get(mid, "Nano Banana Pro")
        elif "2.5-flash-image" in mid:
            label = labels.get(mid, "Nano Banana")
        create.append(_entry(mid, label))
    return {"create": create} if create else {}


def discover_minimax() -> dict[str, list[dict[str, str]]]:
    """Expose documented image models when a key is configured (no probe request)."""
    if not get_minimax_api_key():
        return {}
    return {"create": _entries(_MINIMAX_IMAGE_MODELS)}


def discover_fal() -> dict[str, list[dict[str, str]]]:
    if not get_fal_api_key():
        return {}
    return {
        "create": _entries(_FAL_CREATE_MODELS),
        "extend": [_entry("fal-outpaint", "Fal Outpaint")],
        "manipulate": [_entry("fal-gemini-edit", "Fal Gemini Edit")],
    }


def discover_all() -> dict[str, Any]:
    """Probe each configured provider and persist the catalog."""
    providers: dict[str, Any] = {}
    errors: dict[str, str] = {}

    for name, discoverer in (
        ("openai", discover_openai),
        ("gemini", discover_gemini),
        ("minimax", discover_minimax),
        ("fal", discover_fal),
    ):
        try:
            caps = discoverer()
            if caps:
                providers[name] = caps
            elif name == "openai" and get_openai_api_key():
                errors[name] = "No image models found (check API key or account access)."
            elif name == "gemini" and get_gemini_api_key():
                errors[name] = "No image models found (check API key or account access)."
            elif name == "minimax" and get_minimax_api_key():
                errors[name] = "No image models found (check API key or account access)."
        except Exception as e:
            errors[name] = str(e)

    catalog = default_catalog()
    catalog["discovered_at"] = datetime.now(timezone.utc).isoformat()
    for pname, caps in providers.items():
        if pname not in catalog["providers"]:
            catalog["providers"][pname] = {
                "create": [],
                "extend": [],
                "manipulate": [],
            }
        for cap, models in caps.items():
            if models:
                catalog["providers"][pname][cap] = models
    catalog["errors"] = errors
    save_catalog(catalog)
    return catalog
