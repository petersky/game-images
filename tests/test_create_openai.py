"""Tests for OpenAI create API parameter selection."""

from unittest.mock import MagicMock, patch

from game_images.create import _is_gpt_image_model, create_image_openai


def test_is_gpt_image_model() -> None:
    assert _is_gpt_image_model("gpt-image-1.5")
    assert not _is_gpt_image_model("dall-e-3")


@patch("game_images.create.get_openai_api_key", return_value="sk-test")
def test_gpt_image_generate_omits_response_format(_mock_key: MagicMock) -> None:
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = [MagicMock(b64_json="aW1n", url=None)]
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
def test_dalle3_generate_uses_response_format(_mock_key: MagicMock) -> None:
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.data = [MagicMock(b64_json="aW1n", url=None)]
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
    assert kwargs["response_format"] == "b64_json"
