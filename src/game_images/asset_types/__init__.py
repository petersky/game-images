"""Pluggable asset type registry."""

from game_images.asset_types.base import (
    EDIT_TOOL_CAPABILITIES,
    WORKFLOW_STEP_CAPABILITIES,
    AssetTypeDefinition,
    AssetTypeRegistry,
    AssetTypeUI,
)
from game_images.asset_types.builtin import register_builtin_types

_registry: AssetTypeRegistry | None = None


def get_asset_type_registry() -> AssetTypeRegistry:
    global _registry
    if _registry is None:
        _registry = AssetTypeRegistry()
        register_builtin_types(_registry)
    return _registry


__all__ = [
    "AssetTypeDefinition",
    "AssetTypeRegistry",
    "AssetTypeUI",
    "EDIT_TOOL_CAPABILITIES",
    "WORKFLOW_STEP_CAPABILITIES",
    "get_asset_type_registry",
    "register_builtin_types",
]
