"""Tests for local API key settings."""

import json
import os
from pathlib import Path

import pytest

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


def test_update_and_read_keys(settings_file: Path) -> None:
    settings_mod.update_keys(openai_api_key="sk-test-openai-key")
    assert settings_mod.get_openai_api_key() == "sk-test-openai-key"
    status = settings_mod.keys_status()
    assert status["openai"]["set"] is True
    assert status["openai"]["from_env"] is False
    assert "sk-t" in status["openai"]["hint"]


def test_remove_key(settings_file: Path) -> None:
    settings_mod.update_keys(openai_api_key="sk-remove-me")
    settings_mod.update_keys(openai_api_key="")
    assert settings_mod.get_openai_api_key() is None
    assert not settings_file.read_text().strip() or "openai_api_key" not in settings_file.read_text()


def test_env_overrides_stored(settings_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings_mod.update_keys(fal_api_key="stored-fal")
    monkeypatch.setenv("FAL_KEY", "env-fal")
    assert settings_mod.get_fal_api_key() == "env-fal"
    status = settings_mod.keys_status()
    assert status["fal"]["from_env"] is True


def test_gemini_and_minimax_keys(settings_file: Path) -> None:
    settings_mod.update_keys(gemini_api_key="g-test", minimax_api_key="m-test")
    assert settings_mod.get_gemini_api_key() == "g-test"
    assert settings_mod.get_minimax_api_key() == "m-test"
    status = settings_mod.keys_status()
    assert status["gemini"]["set"] is True
    assert status["minimax"]["set"] is True
