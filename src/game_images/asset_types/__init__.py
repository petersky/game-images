"""Pluggable asset type registry."""

from game_images.asset_types.base import (
    EDIT_TOOL_CAPABILITIES,
    WORKFLOW_STEP_CAPABILITIES,
    AssetTypeDefinition,
    AssetTypeRegistry,
    AssetTypeUI,
)
from game_images.asset_types.builtin import register_builtin_types
from game_images.asset_types.loader import load_entry_point_types

_registry: AssetTypeRegistry | None = None


def get_asset_type_registry(*, reload: bool = False) -> AssetTypeRegistry:
    global _registry
    if _registry is None or reload:
        _registry = AssetTypeRegistry()
        register_builtin_types(_registry)
        load_entry_point_types(_registry)
    return _registry


def reset_asset_type_registry() -> None:
    """Clear cached registry (for tests)."""
    global _registry
    _registry = None


__all__ = [
    "AssetTypeDefinition",
    "AssetTypeRegistry",
    "AssetTypeUI",
    "EDIT_TOOL_CAPABILITIES",
    "WORKFLOW_STEP_CAPABILITIES",
    "get_asset_type_registry",
    "load_entry_point_types",
    "register_builtin_types",
    "reset_asset_type_registry",
]
