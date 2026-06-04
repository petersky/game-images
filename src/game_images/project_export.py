"""Project export presets and zip pack building."""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any

from game_images.library import Library, sanitize_filename

EXPORT_PRESETS: dict[str, dict[str, Any]] = {
    "png_by_role": {
        "label": "PNG by role",
        "description": "All project assets as PNG files named by role or filename.",
    },
    "texture_set": {
        "label": "Texture set",
        "description": "Albedo, normal, roughness, bump, height, and AO maps only.",
        "roles": ["albedo", "normal", "roughness", "bump", "height", "ao"],
    },
    "skydome_pack": {
        "label": "Skydome pack",
        "description": "Skydome main and background assets.",
        "roles": ["skydome_main", "background"],
    },
}


def list_export_presets() -> list[dict[str, Any]]:
    return [
        {"id": preset_id, **meta}
        for preset_id, meta in EXPORT_PRESETS.items()
    ]


def _zip_entry_name(asset: dict[str, Any], used: set[str]) -> str:
    role = (asset.get("role") or "").strip()
    filename = asset.get("filename") or asset.get("asset_id", "asset")
    base = sanitize_filename(role + ".png" if role else filename)
    if not base.lower().endswith(".png"):
        base += ".png"
    stem = Path(base).stem
    suffix = Path(base).suffix or ".png"
    candidate = base
    n = 2
    while candidate.lower() in used:
        candidate = f"{stem}_{n}{suffix}"
        n += 1
    used.add(candidate.lower())
    return candidate


def _safe_project_slug(name: str) -> str:
    slug = re.sub(r"[^\w.\-]+", "_", (name or "project").strip())
    return slug.strip("_") or "project"


def build_project_export_zip(
    library: Library,
    project: dict[str, Any],
    preset_id: str,
) -> tuple[bytes, str]:
    """Build a zip archive for a project export preset."""
    preset = EXPORT_PRESETS.get(preset_id)
    if preset is None:
        raise ValueError(f"Unknown export preset: {preset_id}")

    assets: list[dict[str, Any]] = list(project.get("assets") or [])
    allowed_roles = preset.get("roles")
    if allowed_roles:
        allowed = set(allowed_roles)
        assets = [a for a in assets if (a.get("role") or "") in allowed]

    if not assets:
        raise ValueError("No assets match this export preset.")

    buf = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for asset in assets:
            asset_id = asset.get("asset_id") or asset.get("id")
            if not asset_id:
                continue
            data = library.get_image(asset_id)
            if not data:
                continue
            entry_name = _zip_entry_name(asset, used_names)
            zf.writestr(entry_name, data)

    slug = _safe_project_slug(project.get("name", "project"))
    filename = f"{slug}_{preset_id}.zip"
    return buf.getvalue(), filename
