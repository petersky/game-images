"""Pluggable asset type definitions and capability registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Edit tool id -> required capability
EDIT_TOOL_CAPABILITIES: dict[str, str] = {
    "adjust": "image.adjust",
    "tile": "image.tile",
    "maps": "texture.maps",
    "prepare": "image.prepare",
    "zoom": "image.zoom",
    "extend": "image.extend",
    "manipulate": "image.manipulate",
}

# Game workflow step -> required capability (any one of list)
WORKFLOW_STEP_CAPABILITIES: dict[str, list[str]] = {
    "create": ["image.create"],
    "tile": ["image.tile"],
    "manipulate": ["image.manipulate"],
    "maps": ["texture.maps"],
    "zoom": ["image.zoom"],
    "extend": ["image.extend"],
    "adjust": ["image.adjust"],
    "prepare": ["image.prepare"],
}


@dataclass(frozen=True)
class AssetTypeUI:
    """Optional UI hooks (phase 2+)."""

    preview_modes: tuple[str, ...] = ()
    workflow_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssetTypeDefinition:
    id: str
    label: str
    description: str = ""
    extends: str | None = None
    capabilities: frozenset[str] = frozenset()
    default_filename_suffix: str | None = None
    ui: AssetTypeUI = field(default_factory=AssetTypeUI)

    def to_dict(self, *, merged_capabilities: frozenset[str] | None = None) -> dict[str, Any]:
        caps = merged_capabilities if merged_capabilities is not None else self.capabilities
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "extends": self.extends,
            "capabilities": sorted(caps),
            "default_filename_suffix": self.default_filename_suffix,
            "preview_modes": list(self.ui.preview_modes),
            "workflow_ids": list(self.ui.workflow_ids),
        }


class AssetTypeRegistry:
    def __init__(self) -> None:
        self._types: dict[str, AssetTypeDefinition] = {}

    def register(self, defn: AssetTypeDefinition) -> None:
        if defn.id in self._types:
            raise ValueError(f"Asset type already registered: {defn.id}")
        self._types[defn.id] = defn

    def get(self, type_id: str) -> AssetTypeDefinition:
        if type_id not in self._types:
            return self._types.get("generic_image") or next(iter(self._types.values()))
        return self._types[type_id]

    def capabilities_for(self, type_id: str) -> frozenset[str]:
        seen: set[str] = set()
        current_id: str | None = type_id
        while current_id:
            defn = self._types.get(current_id)
            if defn is None:
                break
            seen.update(defn.capabilities)
            current_id = defn.extends
        if not seen and "generic_image" in self._types:
            return self.capabilities_for("generic_image")
        return frozenset(seen)

    def list_types(self) -> list[AssetTypeDefinition]:
        return list(self._types.values())

    def list_public(self) -> list[dict[str, Any]]:
        return [
            defn.to_dict(merged_capabilities=self.capabilities_for(defn.id))
            for defn in self.list_types()
        ]

    def has_capability(self, type_id: str, capability: str) -> bool:
        return capability in self.capabilities_for(type_id)

    def edit_tools_for(self, type_id: str) -> list[str]:
        caps = self.capabilities_for(type_id)
        return [
            tool
            for tool, cap in EDIT_TOOL_CAPABILITIES.items()
            if cap in caps
        ]
