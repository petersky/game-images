"""Tests for asset type entry point loading."""

from game_images.asset_types.base import AssetTypeDefinition, AssetTypeRegistry
from game_images.asset_types.loader import load_entry_point_types


def _register_demo(registry: AssetTypeRegistry) -> None:
    registry.register(
        AssetTypeDefinition(
            id="plugin_demo",
            label="Plugin Demo",
            capabilities=frozenset({"demo.preview"}),
        )
    )


class _FakeEntryPoint:
    def __init__(self, name: str, fn) -> None:
        self.name = name
        self._fn = fn

    def load(self):
        return self._fn


def test_load_entry_point_types() -> None:
    registry = AssetTypeRegistry()
    loaded = load_entry_point_types(
        registry,
        entry_points=[_FakeEntryPoint("plugin_demo", _register_demo)],
    )
    assert loaded == ["plugin_demo"]
    assert registry.get("plugin_demo").label == "Plugin Demo"
    assert "demo.preview" in registry.capabilities_for("plugin_demo")
