"""Turn provider and API exceptions into structured, user-facing error payloads."""

from __future__ import annotations

import ast
import json
import re
from typing import Any

# OpenAI: "Error code: 400 - {'error': {...}}"
_OPENAI_PREFIX = re.compile(
    r"^Error code:\s*(\d+)\s*-\s*(.+)$",
    re.DOTALL,
)
# Gemini google-genai: "429 RESOURCE_EXHAUSTED. {'error': {...}}"
_GEMINI_PREFIX = re.compile(
    r"^(\d{3})\s+([A-Z_]+)\.\s*(.+)$",
    re.DOTALL,
)
_MINIMAX_PREFIX = re.compile(r"^MiniMax API error \((\d+)\):\s*(.+)$", re.DOTALL)


def _try_parse_python_dict(s: str) -> dict[str, Any] | None:
    s = s.strip()
    if not s.startswith("{"):
        return None
    try:
        val = ast.literal_eval(s)
        return val if isinstance(val, dict) else None
    except (SyntaxError, ValueError):
        pass
    try:
        val = json.loads(s)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        return None


def _nested_message(payload: dict[str, Any]) -> str | None:
    err = payload.get("error")
    if isinstance(err, dict):
        msg = err.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()
    msg = payload.get("message")
    if isinstance(msg, str) and msg.strip():
        return msg.strip()
    return None


def _nested_code(payload: dict[str, Any]) -> str | None:
    err = payload.get("error")
    if isinstance(err, dict):
        for key in ("code", "type", "status"):
            val = err.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _gemini_quota_hint(payload: dict[str, Any]) -> str | None:
    err = payload.get("error")
    if not isinstance(err, dict):
        return None
    details = err.get("details")
    if not isinstance(details, list):
        return None
    models: list[str] = []
    retry_s: float | None = None
    for item in details:
        if not isinstance(item, dict):
            continue
        if item.get("@type", "").endswith("RetryInfo"):
            delay = item.get("retryDelay", "")
            if isinstance(delay, str) and delay.endswith("s"):
                try:
                    retry_s = float(delay[:-1])
                except ValueError:
                    pass
        if item.get("@type", "").endswith("QuotaFailure"):
            for v in item.get("violations") or []:
                if isinstance(v, dict):
                    dims = v.get("quotaDimensions") or {}
                    model = dims.get("model")
                    if model and model not in models:
                        models.append(str(model))
    parts: list[str] = []
    if models:
        parts.append("Model(s): " + ", ".join(models))
    if retry_s is not None and retry_s > 0:
        parts.append(f"Try again in about {int(retry_s + 0.5)} seconds.")
    return ". ".join(parts) if parts else None


def _friendly_summary(
    *,
    provider: str | None,
    http_status: int | None,
    code: str | None,
    message: str | None,
) -> str:
    text = (message or "").lower()
    code_l = (code or "").lower()

    if code_l == "billing_hard_limit_reached" or "billing hard limit" in text:
        return "OpenAI billing limit reached"
    if code_l == "insufficient_quota" or "exceeded your current quota" in text:
        if provider == "gemini":
            return "Gemini API quota exceeded"
        return "API quota exceeded"
    if http_status == 429 or code_l == "resource_exhausted" or "rate limit" in text:
        if provider == "gemini":
            return "Gemini rate or quota limit reached"
        return "Rate or quota limit reached"
    if (
        "api.model.images.request" in text
        or "missing scopes" in text
    ):
        return "ChatGPT sign-in cannot use Images API"
    if http_status in (401, 403) or "invalid api key" in text or "incorrect api key" in text:
        return "API key rejected"
    if http_status == 400 and provider == "openai":
        return "OpenAI request rejected"
    if provider == "minimax":
        return "MiniMax request failed"
    if provider == "gemini":
        return "Gemini request failed"
    if provider == "openai":
        return "OpenAI request failed"
    if provider == "fal":
        return "Fal request failed"
    return "Provider request failed"


def _friendly_message(
    *,
    provider: str | None,
    http_status: int | None,
    code: str | None,
    message: str | None,
    extra: str | None = None,
) -> str:
    hints: list[str] = []
    text = message or ""
    code_l = (code or "").lower()

    if code_l == "billing_hard_limit_reached" or "billing hard limit" in text.lower():
        hints.append(
            "Your OpenAI account hit its billing hard limit. Add credits or raise the limit "
            "in the OpenAI dashboard, then try again."
        )
    elif provider == "gemini" and (
        http_status == 429
        or code_l == "resource_exhausted"
        or "quota" in text.lower()
        or "free_tier" in text.lower()
    ):
        hints.append(
            "Gemini image generation is not available on your current quota (free tier may be "
            "disabled or exhausted). Enable billing in Google AI Studio or pick another provider."
        )
        if text and "quota" not in hints[0].lower():
            hints.append(text.split("\n")[0].strip())
    elif http_status == 429 or "rate limit" in text.lower():
        hints.append("Too many requests. Wait a moment and try again.")
        if text:
            hints.append(text.split("\n")[0].strip())
    elif "api.model.images.request" in text.lower() or "missing scopes" in text.lower():
        hints.append(
            "ChatGPT sign-in (OAuth) does not include access to the OpenAI Images API "
            "(scope api.model.images.request). Images on chatgpt.com use a different "
            "service. Use a platform API key from https://platform.openai.com/api-keys. "
            'In Settings, set "Use for OpenAI requests" to API key only and save your key.'
        )
    elif http_status in (401, 403):
        hints.append("Check the API key in Settings (gear icon) or your environment variables.")
    elif message:
        # Use first line only for display; full text stays in raw
        first = text.split("\n")[0].strip()
        if len(first) > 280:
            first = first[:277] + "…"
        hints.append(first)
    else:
        hints.append("The provider returned an error. Expand technical details below for more.")

    if extra:
        hints.append(extra)
    return " ".join(hints)


def _detect_provider(raw: str, mod: str) -> str | None:
    mod_l = mod.lower()
    raw_l = raw.lower()
    if "openai" in mod_l or "billing_hard_limit" in raw_l or "error code:" in raw_l:
        return "openai"
    if "genai" in mod_l or "google" in mod_l or "resource_exhausted" in raw_l:
        return "gemini"
    if "minimax" in mod_l or "minimax api error" in raw_l:
        return "minimax"
    if "fal" in mod_l:
        return "fal"
    return None


def format_exception(e: Exception) -> dict[str, Any]:
    """Build a JSON-serializable error object for HTTP responses and the web UI."""
    if isinstance(e, ValueError):
        msg = str(e).strip() or "Invalid request"
        return {
            "summary": "Invalid request",
            "message": msg,
            "provider": None,
            "status": 400,
            "code": None,
            "raw": msg,
        }

    raw = str(e).strip() or type(e).__name__
    mod = type(e).__module__
    provider = _detect_provider(raw, mod)
    http_status: int | None = None
    code: str | None = None
    message: str | None = None
    extra: str | None = None
    payload: dict[str, Any] | None = None

    m = _OPENAI_PREFIX.match(raw)
    if m:
        provider = provider or "openai"
        http_status = int(m.group(1))
        payload = _try_parse_python_dict(m.group(2))
    else:
        m = _GEMINI_PREFIX.match(raw)
        if m:
            provider = provider or "gemini"
            http_status = int(m.group(1))
            code = m.group(2)
            payload = _try_parse_python_dict(m.group(3))
        else:
            m = _MINIMAX_PREFIX.match(raw)
            if m:
                provider = provider or "minimax"
                http_status = int(m.group(1))
                message = m.group(2).strip()
            elif raw.startswith("Provider API error: "):
                return format_exception(
                    type(e)(raw.removeprefix("Provider API error: ").strip())
                )

    if payload:
        message = _nested_message(payload) or message
        code = _nested_code(payload) or code
        if provider == "gemini":
            extra = _gemini_quota_hint(payload)

    summary = _friendly_summary(
        provider=provider,
        http_status=http_status,
        code=code,
        message=message,
    )
    display_message = _friendly_message(
        provider=provider,
        http_status=http_status,
        code=code,
        message=message,
        extra=extra,
    )

    return {
        "summary": summary,
        "message": display_message,
        "provider": provider,
        "status": http_status,
        "code": code,
        "raw": raw,
    }


def format_exception_for_http(e: Exception) -> tuple[int, dict[str, Any]]:
    """Map exception to HTTP status and structured detail body."""
    body = format_exception(e)
    if isinstance(e, ValueError):
        return 400, body
    mod = type(e).__module__.lower()
    if (
        "openai" in mod
        or "fal" in mod
        or "google" in mod
        or "genai" in mod
        or body.get("provider")
    ):
        status = body.get("status")
        if isinstance(status, int) and 400 <= status < 600:
            return status, body
        return 502, body
    if isinstance(e, (RuntimeError, OSError)):
        return 502, body
    return 500, {
        "summary": "Unexpected error",
        "message": str(e).strip() or "An unexpected error occurred.",
        "provider": None,
        "status": 500,
        "code": None,
        "raw": str(e),
    }
