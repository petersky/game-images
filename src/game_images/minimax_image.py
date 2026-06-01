"""MiniMax text-to-image generation API."""

from __future__ import annotations

import base64
import io
import json
import os
import urllib.error
import urllib.request

from PIL import Image

from game_images.settings import get_minimax_api_key

_MINIMAX_IMAGE_URL = "https://api.minimax.io/v1/image_generation"


def _aspect_ratio(width: int, height: int) -> str:
    if height <= 0:
        return "1:1"
    r = width / height
    if r > 1.6:
        return "16:9"
    if r < 0.65:
        return "9:16"
    if r > 1.2:
        return "4:3"
    if r < 0.85:
        return "3:4"
    return "1:1"


def _resize_to_png(image_bytes: bytes, width: int, height: int) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    if img.size != (width, height):
        img = img.resize((width, height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _extract_image_bytes(payload: dict) -> bytes:
    data = payload.get("data") or {}
    if isinstance(data.get("image_base64"), list) and data["image_base64"]:
        return base64.b64decode(data["image_base64"][0])
    if isinstance(data.get("image_base64"), str) and data["image_base64"]:
        return base64.b64decode(data["image_base64"])
    images = data.get("images") or data.get("image_urls")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, str) and first.startswith("http"):
            with urllib.request.urlopen(first) as r:
                return r.read()
        if isinstance(first, dict):
            b64 = first.get("base64") or first.get("image_base64")
            if b64:
                return base64.b64decode(b64)
            url = first.get("url")
            if url:
                with urllib.request.urlopen(url) as r:
                    return r.read()
    raise RuntimeError("MiniMax response contained no image data")


def create_image_minimax(
    prompt: str,
    width: int,
    height: int,
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> bytes:
    key = api_key or get_minimax_api_key()
    if not key:
        raise ValueError(
            "MiniMax API key not set. Add it in Settings (gear icon) or set MINIMAX_API_KEY."
        )
    model = (model or "image-01").strip()
    w = max(512, min(2048, width))
    h = max(512, min(2048, height))

    body = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": _aspect_ratio(w, h),
            "response_format": "base64",
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        _MINIMAX_IMAGE_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MiniMax API error ({e.code}): {detail}") from e

    base = payload.get("base_resp") or {}
    if base.get("status_code", 0) != 0:
        raise RuntimeError(
            base.get("status_msg") or f"MiniMax error code {base.get('status_code')}"
        )

    raw = _extract_image_bytes(payload)
    return _resize_to_png(raw, w, h)
