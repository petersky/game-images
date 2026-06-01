"""Text-to-image creation via OpenAI and Fal."""

from __future__ import annotations

import base64
import io
import os
import urllib.request
from typing import Literal

from PIL import Image

from game_images.settings import get_fal_api_key, get_openai_api_key

ProviderName = Literal["openai", "fal"]

# OpenAI generation sizes (pick closest, then resize)
_OPENAI_DALLE3_SIZES = ((1024, 1024), (1792, 1024), (1024, 1792))
_OPENAI_DALLE2_SIZES = ((256, 256), (512, 512), (1024, 1024))
_GPT_IMAGE_SIZES = ((1024, 1024), (1024, 1536), (1536, 1024))


def _is_gpt_image_model(model: str) -> bool:
    return model.startswith("gpt-image")


def _resize_to_png(image_bytes: bytes, width: int, height: int) -> bytes:
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    if img.size != (width, height):
        img = img.resize((width, height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _nearest_size(
    width: int,
    height: int,
    options: tuple[tuple[int, int], ...],
) -> str | tuple[int, int]:
    """Return OpenAI size string or (w,h) for Fal."""
    best = options[0]
    best_dist = float("inf")
    for ow, oh in options:
        dist = abs(ow - width) + abs(oh - height)
        if dist < best_dist:
            best_dist = dist
            best = (ow, oh)
    if len(options) == 3 and all(s[0] == s[1] for s in options):
        return f"{best[0]}x{best[1]}"
    return f"{best[0]}x{best[1]}"


def _download_openai_first(resp) -> bytes:
    if not resp.data:
        raise RuntimeError("OpenAI generate returned no image")
    first = resp.data[0]
    if getattr(first, "b64_json", None):
        return base64.b64decode(first.b64_json)
    if getattr(first, "url", None):
        with urllib.request.urlopen(first.url) as r:
            return r.read()
    raise RuntimeError("OpenAI response had no b64_json or url")


def create_image_openai(
    prompt: str,
    width: int,
    height: int,
    *,
    model: str | None = None,
    api_key: str | None = None,
) -> bytes:
    from openai import OpenAI

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError(
            "OpenAI API key not set. Add it in Settings (gear icon) or set OPENAI_API_KEY."
        )
    model = model or os.environ.get("OPENAI_IMAGE_MODEL") or "dall-e-3"
    client = OpenAI(api_key=key)
    w = max(64, min(2048, width))
    h = max(64, min(2048, height))

    if model.startswith("dall-e-3"):
        size = _nearest_size(w, h, _OPENAI_DALLE3_SIZES)
        resp = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size,  # type: ignore[arg-type]
            n=1,
            response_format="b64_json",
        )
    elif _is_gpt_image_model(model):
        # GPT image models always return base64; response_format is not supported.
        size = _nearest_size(w, h, _GPT_IMAGE_SIZES)
        resp = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,  # type: ignore[arg-type]
            n=1,
        )
    else:
        size = _nearest_size(w, h, _OPENAI_DALLE2_SIZES)
        resp = client.images.generate(
            model="dall-e-2",
            prompt=prompt,
            size=size,  # type: ignore[arg-type]
            n=1,
            response_format="b64_json",
        )
    raw = _download_openai_first(resp)
    return _resize_to_png(raw, w, h)


def create_image_fal(
    prompt: str,
    width: int,
    height: int,
    *,
    api_key: str | None = None,
) -> bytes:
    import fal_client

    key = api_key or os.environ.get("FAL_KEY")
    if not key:
        raise ValueError(
            "Fal API key not set. Add it in Settings (gear icon) or set FAL_KEY."
        )
    w = max(64, min(2048, width))
    h = max(64, min(2048, height))
    result = fal_client.subscribe(
        "fal-ai/flux/schnell",
        arguments={
            "prompt": prompt,
            "image_size": {"width": w, "height": h},
            "num_images": 1,
        },
    )
    images = result.get("images") or []
    if not images:
        raise RuntimeError("Fal generate returned no images")
    url = images[0].get("url")
    if not url:
        raise RuntimeError("Fal image had no url")
    with urllib.request.urlopen(url) as r:
        raw = r.read()
    return _resize_to_png(raw, w, h)


def create_image(
    prompt: str,
    width: int,
    height: int,
    provider_name: ProviderName = "openai",
    *,
    model: str | None = None,
) -> bytes:
    """Generate a new image from a text prompt."""
    if not prompt.strip():
        raise ValueError("Prompt is required")
    if provider_name == "openai":
        return create_image_openai(
            prompt, width, height, model=model, api_key=get_openai_api_key()
        )
    if provider_name == "fal":
        return create_image_fal(prompt, width, height, api_key=get_fal_api_key())
    raise ValueError(f"Unknown provider: {provider_name}")
