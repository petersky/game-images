"""Gemini API (Nano Banana) text-to-image generation."""

from __future__ import annotations

import io
import os

from PIL import Image

from game_images.settings import get_gemini_api_key

# aspect_ratio values supported by Gemini image models
_ASPECT_RATIOS = (
    (1.0, "1:1"),
    (16 / 9, "16:9"),
    (9 / 16, "9:16"),
    (4 / 3, "4:3"),
    (3 / 4, "3:4"),
    (3 / 2, "3:2"),
    (2 / 3, "2:3"),
)


def _aspect_ratio(width: int, height: int) -> str:
    if height <= 0:
        return "1:1"
    target = width / height
    best = _ASPECT_RATIOS[0][1]
    best_dist = float("inf")
    for ratio, label in _ASPECT_RATIOS:
        dist = abs(ratio - target)
        if dist < best_dist:
            best_dist = dist
            best = label
    return best


def _image_size_label(width: int, height: int) -> str:
    px = max(width, height)
    if px >= 3000:
        return "4K"
    if px >= 1500:
        return "2K"
    return "1K"


def _pil_to_png_bytes(img: Image.Image, width: int, height: int) -> bytes:
    img = img.convert("RGBA")
    if img.size != (width, height):
        img = img.resize((width, height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_image_gemini(
    prompt: str,
    width: int,
    height: int,
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> bytes:
    from google import genai
    from google.genai import types

    key = api_key or get_gemini_api_key()
    if not key:
        raise ValueError(
            "Gemini API key not set. Add it in Settings (gear icon) or set GEMINI_API_KEY."
        )
    model = (model or os.environ.get("GEMINI_IMAGE_MODEL") or "gemini-2.5-flash-image").strip()
    w = max(64, min(4096, width))
    h = max(64, min(4096, height))

    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=model,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=_aspect_ratio(w, h),
                image_size=_image_size_label(w, h),
            ),
        ),
    )

    for part in response.parts:
        if part.inline_data is not None:
            if hasattr(part, "as_image"):
                return _pil_to_png_bytes(part.as_image(), w, h)
            data = getattr(part.inline_data, "data", None)
            if data:
                import base64

                raw = base64.b64decode(data)
                return _pil_to_png_bytes(Image.open(io.BytesIO(raw)), w, h)

    raise RuntimeError("Gemini returned no image in the response")
