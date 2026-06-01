"""Tests for provider error formatting."""

from game_images.api_errors import format_exception


def test_openai_billing_limit() -> None:
    raw = (
        "Error code: 400 - {'error': {'message': 'Billing hard limit has been reached.', "
        "'type': 'billing_limit_user_error', 'param': None, 'code': 'billing_hard_limit_reached'}}"
    )
    body = format_exception(Exception(raw))
    assert body["summary"] == "OpenAI billing limit reached"
    assert "OpenAI dashboard" in body["message"]
    assert body["provider"] == "openai"
    assert body["code"] == "billing_hard_limit_reached"


def test_gemini_quota_exhausted() -> None:
    raw = (
        "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota.', "
        "'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': 'type.googleapis.com/google.rpc.RetryInfo', "
        "'retryDelay': '8s'}]}}"
    )
    body = format_exception(Exception(raw))
    assert "quota" in body["summary"].lower() or "limit" in body["summary"].lower()
    assert body["provider"] == "gemini"
    assert "8 seconds" in body["message"] or "billing" in body["message"].lower()


def test_openai_oauth_missing_image_scope() -> None:
    raw = (
        "Error code: 401 - {'error': {'message': "
        "'You have insufficient permissions for this operation. Missing scopes: "
        "api.model.images.request. Check that you have the correct role', "
        "'type': 'invalid_request_error', 'param': None, 'code': None}}"
    )
    body = format_exception(Exception(raw))
    assert "Images API" in body["summary"]
    assert "platform.openai.com/api-keys" in body["message"]
    assert body["status"] == 401


def test_value_error() -> None:
    body = format_exception(ValueError("Prompt is required"))
    assert body["summary"] == "Invalid request"
    assert body["message"] == "Prompt is required"


def test_gemini_free_tier_zero_limit_snippet() -> None:
    raw = (
        "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': "
        "'You exceeded your current quota, please check your plan and billing details.', "
        "'status': 'RESOURCE_EXHAUSTED', 'details': [{'@type': "
        "'type.googleapis.com/google.rpc.QuotaFailure', 'violations': [{'quotaMetric': "
        "'generativelanguage.googleapis.com/generate_content_free_tier_requests', "
        "'quotaDimensions': {'model': 'gemini-2.5-flash-preview-image'}}]}, "
        "{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '7.627877704s'}]}}"
    )
    body = format_exception(Exception(raw))
    assert body["provider"] == "gemini"
    assert "gemini-2.5-flash-preview-image" in body["message"]
    assert "quota" in body["summary"].lower() or "limit" in body["summary"].lower()
