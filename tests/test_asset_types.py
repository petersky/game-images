"""Tests for asset type registry."""

from game_images.asset_types import get_asset_type_registry


def test_registry_builtin_types() -> None:
    reg = get_asset_type_registry()
    ids = {t.id for t in reg.list_types()}
    assert ids >= {"generic_image", "texture", "skydome", "background"}


def test_texture_inherits_image_capabilities() -> None:
    reg = get_asset_type_registry()
    caps = reg.capabilities_for("texture")
    assert "image.manipulate" in caps
    assert "texture.maps" in caps
    assert "skydome.preview" not in caps


def test_skydome_has_skydome_caps() -> None:
    reg = get_asset_type_registry()
    caps = reg.capabilities_for("skydome")
    assert "skydome.preview" in caps
    assert "texture.maps" not in caps


def test_edit_tools_for_texture() -> None:
    reg = get_asset_type_registry()
    tools = reg.edit_tools_for("texture")
    assert "maps" in tools
    assert "manipulate" in tools


def test_background_no_texture_maps() -> None:
    reg = get_asset_type_registry()
    tools = reg.edit_tools_for("background")
    assert "maps" not in tools
    assert "extend" in tools
