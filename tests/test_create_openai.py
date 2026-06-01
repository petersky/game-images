"""Tests for OpenAI create API parameter selection."""

import base64
from unittest.mock import MagicMock, patch

from game_images.create import (
    DEFAULT_OPENAI_CREATE_MODEL,
    _is_gpt_image_model,
    create_image_openai,
)

# Minimal valid 1x1 PNG
_MINI_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_is_gpt_image_model() -> None:
    assert _is_gpt_image_model("gpt-image-1.5")
    assert not _is_gpt_image_model("dall-e-3")


@patch("game_images.create.get_openai_api_key", return_value="sk-test")
def test_gpt_image_generate_omits_response_format(_mock_key: MagicMock) -> None:
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = [
        MagicMock(b64_json=base64.b64encode(_MINI_PNG).decode(), url=None)
    ]
    mock_client.images.generate.return_value = mock_resp

    with patch("openai.OpenAI", return_value=mock_client):
        create_image_openai(
            "a cat",
            1024,
            1024,
            model="gpt-image-1.5",
            api_key="sk-test",
        )

    kwargs = mock_client.images.generate.call_args.kwargs
    assert kwargs["model"] == "gpt-image-1.5"
    assert "response_format" not in kwargs


@patch("game_images.create.get_openai_api_key", return_value="sk-test")
def test_dalle3_generate_omits_response_format(_mock_key: MagicMock) -> None:
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = [
        MagicMock(b64_json=base64.b64encode(_MINI_PNG).decode(), url=None)
    ]
    mock_client.images.generate.return_value = mock_resp

    with patch("openai.OpenAI", return_value=mock_client):
        create_image_openai(
            "a cat",
            1024,
            1024,
            model="dall-e-3",
            api_key="sk-test",
        )

    kwargs = mock_client.images.generate.call_args.kwargs
    assert kwargs["model"] == "dall-e-3"
    assert "response_format" not in kwargs


@patch("game_images.create.get_openai_api_key", return_value="sk-test")
def test_dalle3_falls_back_when_model_missing(_mock_key: MagicMock) -> None:
    mock_client = MagicMock()
    ok_resp = MagicMock()
    ok_resp.data = [
        MagicMock(b64_json=base64.b64encode(_MINI_PNG).decode(), url=None)
    ]

    def generate_side_effect(**kwargs):
        if kwargs.get("model") == "dall-e-3":
            raise RuntimeError(
                "Error code: 400 - model 'dall-e-3' does not exist"
            )
        mock_client.images.generate.return_value = ok_resp
        return ok_resp

    mock_client.images.generate.side_effect = generate_side_effect

    with patch("openai.OpenAI", return_value=mock_client):
        create_image_openai(
            "a cat",
            1024,
            1024,
            model="dall-e-3",
            api_key="sk-test",
        )

    calls = [c.kwargs["model"] for c in mock_client.images.generate.call_args_list]
    assert calls == ["dall-e-3", "gpt-image-1.5"]


def test_default_model_is_gpt_image() -> None:
    assert DEFAULT_OPENAI_CREATE_MODEL == "gpt-image-1.5"
