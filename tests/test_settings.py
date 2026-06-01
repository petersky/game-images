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


def test_openai_oauth_token(settings_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_OAUTH_TOKEN", raising=False)
    settings_mod.update_keys(openai_oauth_token="oauth-token-value")
    assert settings_mod.get_openai_credential() == "oauth-token-value"
    status = settings_mod.keys_status()["openai"]
    assert status["auth_method"] == "oauth"
    assert status["oauth_stored"] is True


def test_openai_oauth_session(settings_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings_mod.save_openai_oauth_session(
        {
            "access_token": "access-tok",
            "refresh_token": "refresh-tok",
            "expires_at": 9999999999,
            "account_id": "acct-1",
        }
    )
    assert settings_mod.get_openai_oauth_access_token() == "access-tok"
    status = settings_mod.keys_status()["openai"]
    assert status["oauth_session"] is True


def test_openai_api_key_over_oauth(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_OAUTH_TOKEN", raising=False)
    settings_mod.save_openai_oauth_session(
        {
            "access_token": "oauth-access",
            "refresh_token": "oauth-refresh",
            "expires_at": 9999999999,
        }
    )
    settings_mod.update_keys(openai_api_key="sk-stored-key")
    assert settings_mod.get_openai_credential() == "sk-stored-key"
    settings_mod.update_keys(openai_auth_mode="oauth")
    assert settings_mod.get_openai_credential() == "oauth-access"
    assert settings_mod.openai_active_auth() == "oauth_session"
    settings_mod.update_keys(openai_auth_mode="api_key")
    assert settings_mod.get_openai_credential() == "sk-stored-key"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
    assert settings_mod.get_openai_credential() == "sk-env-key"


def test_validate_openai_images_rejects_oauth(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings_mod.update_keys(openai_auth_mode="oauth", openai_oauth_token="eyJ.fake.jwt")
    with pytest.raises(ValueError, match="api.model.images.request"):
        settings_mod.validate_openai_images_credential()


def test_validate_openai_images_accepts_api_key(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings_mod.update_keys(openai_api_key="sk-valid-key")
    assert settings_mod.validate_openai_images_credential() == "sk-valid-key"


def test_enrich_openai_auth_oauth_images_note(
    settings_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings_mod.update_keys(openai_auth_mode="oauth", openai_oauth_token="eyJ.fake.jwt")
    status = settings_mod.keys_status()["openai"]
    assert status["oauth_supports_images_api"] is False
    assert "api.model.images.request" in status["images_api_note"]
