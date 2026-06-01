"""Gemini API (Nano Banana) extend and manipulate via image-capable models."""

from __future__ import annotations

import io
import os

from PIL import Image

from game_images.gemini_image import _aspect_ratio, _image_size_label, _pil_to_png_bytes
from game_images.providers.base import Direction
from game_images.providers.openai_provider import (
    _build_outpaint_canvas_and_mask,
    _directions_to_expand,
)
from game_images.settings import get_gemini_api_key


def _extract_image_bytes(response, width: int, height: int) -> bytes:
    for part in response.parts:
        if part.inline_data is not None:
            if hasattr(part, "as_image"):
                return _pil_to_png_bytes(part.as_image(), width, height)
            data = getattr(part.inline_data, "data", None)
            if data:
                import base64

                raw = base64.b64decode(data)
                return _pil_to_png_bytes(Image.open(io.BytesIO(raw)), width, height)
    raise RuntimeError("Gemini returned no image in the response")


def extend_image_gemini_margins(
    image: bytes,
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
    prompt: str,
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
    if left == top == right == bottom == 0:
        return image

    canvas_bytes, mask_bytes = _build_outpaint_canvas_and_mask(
        image, left, top, right, bottom
    )
    with Image.open(io.BytesIO(canvas_bytes)) as canvas:
        w, h = canvas.size

    edit_prompt = (
        prompt
        or "Seamlessly extend the image into the new border areas. Match style, lighting, and content."
    )
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=canvas_bytes, mime_type="image/png"),
            types.Part.from_bytes(data=mask_bytes, mime_type="image/png"),
            edit_prompt,
        ],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=_aspect_ratio(w, h),
                image_size=_image_size_label(w, h),
            ),
        ),
    )
    return _extract_image_bytes(response, w, h)


def extend_image_gemini(
    image: bytes,
    directions: list[Direction],
    amount_px: int,
    prompt: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> bytes:
    left, top, right, bottom = _directions_to_expand(directions, amount_px)
    return extend_image_gemini_margins(
        image,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        prompt=prompt,
        model=model,
        api_key=api_key,
    )


def manipulate_image_gemini(
    image: bytes,
    prompt: str,
    *,
    mask: bytes | None = None,
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
    with Image.open(io.BytesIO(image)) as img:
        w, h = img.size

    parts: list = [types.Part.from_bytes(data=image, mime_type="image/png")]
    if mask is not None:
        parts.append(types.Part.from_bytes(data=mask, mime_type="image/png"))
        parts.append(
            "Edit the first image using the mask (transparent = edit, opaque = keep). "
            + prompt
        )
    else:
        parts.append(prompt)

    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model=model,
        contents=parts,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(
                aspect_ratio=_aspect_ratio(w, h),
                image_size=_image_size_label(w, h),
            ),
        ),
    )
    return _extract_image_bytes(response, w, h)
