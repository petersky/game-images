"""Tests for model discovery catalog."""

from pathlib import Path

import pytest

from game_images import model_catalog as mc
from game_images import settings as settings_mod


@pytest.fixture
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("GAME_IMAGES_LIBRARY", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    return tmp_path / "settings.json"


def test_default_catalog_has_all_providers() -> None:
    cat = mc.default_catalog()
    for name in ("openai", "fal", "gemini", "minimax"):
        assert name in cat["providers"]
        assert cat["providers"][name]["create"]


def test_discover_minimax_without_api_call(settings_file: Path) -> None:
    settings_mod.update_keys(minimax_api_key="mm-test-key")
    caps = mc.discover_minimax()
    assert caps["create"]
    assert caps["create"][0]["id"] == "image-01"


def test_discover_all_persists(settings_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mc, "discover_openai", lambda: {})
    monkeypatch.setattr(
        mc,
        "discover_gemini",
        lambda: {"create": [{"id": "gemini-2.5-flash-image", "label": "Nano Banana"}]},
    )
    monkeypatch.setattr(mc, "discover_minimax", lambda: {})
    monkeypatch.setattr(mc, "discover_fal", lambda: {})
    settings_mod.update_keys(gemini_api_key="g-test")
    result = mc.discover_all()
    assert result["discovered_at"]
    loaded = mc.get_catalog()
    gemini_create = loaded["providers"]["gemini"]["create"]
    assert any(m["id"] == "gemini-2.5-flash-image" for m in gemini_create)
