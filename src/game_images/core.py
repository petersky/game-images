"""Core operations: extend, manipulate, and shift (for extend workflow)."""

import io
from typing import Literal

from PIL import Image

from game_images.create import create_image as _create_image
from game_images.image_ops import adjust_image as _adjust_image
from game_images.image_ops import crop_image as _crop_image
from game_images.image_ops import tile_image as _tile_image
from game_images.providers.base import Direction, Provider
from game_images.providers.fal_provider import FalProvider
from game_images.providers.openai_provider import OpenAIProvider
from game_images.settings import get_fal_api_key, get_openai_credential
from game_images.texture_maps import generate_texture_map as _generate_texture_map

ProviderName = Literal["openai", "fal", "gemini", "minimax"]
_PROVIDERS: dict[ProviderName, type[Provider]] = {
    "openai": OpenAIProvider,
    "fal": FalProvider,
}


def get_provider(name: ProviderName, *, model: str | None = None) -> Provider:
    """Return a provider instance by name. model is used only for OpenAI."""
    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown provider: {name}. Choose from: {list(_PROVIDERS)}")
    if name == "openai":
        return OpenAIProvider(model=model, api_key=get_openai_credential())
    if name == "fal":
        return FalProvider(api_key=get_fal_api_key())
    return cls()


def shift_image(
    image: bytes,
    direction: Direction,
    amount_px: int,
) -> bytes:
    """Shift the image content in the given direction; vacated area becomes black. Same canvas size.

    - West: content moves left (right part of scene slides left), right side becomes black.
    - East: content moves right (left part slides right), left side becomes black.
    - North: content moves up (bottom part slides up), bottom becomes black.
    - South: content moves down (top part slides down), top becomes black.
    """
    img = Image.open(io.BytesIO(image)).convert("RGB")
    w, h = img.size
    n = min(amount_px, w - 1) if direction in ("east", "west") else min(amount_px, h - 1)
    if n <= 0:
        return image
    out = Image.new("RGB", (w, h), (0, 0, 0))
    if direction == "west":
        # Right part of image moves to left; right n pixels black
        out.paste(img.crop((n, 0, w, h)), (0, 0))
    elif direction == "east":
        # Left part of image moves to right; left n pixels black
        out.paste(img.crop((0, 0, w - n, h)), (n, 0))
    elif direction == "north":
        # Bottom part of image moves up; bottom n pixels black
        out.paste(img.crop((0, n, w, h)), (0, 0))
    else:  # south
        # Top part of image moves down; top n pixels black
        out.paste(img.crop((0, 0, w, h - n)), (0, n))
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def extend_image(
    image: bytes,
    directions: list[Direction],
    amount_px: int,
    prompt: str,
    provider_name: ProviderName = "openai",
    *,
    image_format: str = "png",
    model: str | None = None,
) -> bytes:
    """Extend the image in the given direction(s). Returns image bytes."""
    if provider_name == "gemini":
        from game_images.gemini_edit import extend_image_gemini

        return extend_image_gemini(image, directions, amount_px, prompt, model=model)
    if provider_name == "minimax":
        raise ValueError(
            "MiniMax does not support Extend. Choose OpenAI, Gemini, or Fal."
        )
    provider = get_provider(provider_name, model=model)  # type: ignore[arg-type]
    return provider.extend(
        image,
        directions,
        amount_px,
        prompt,
        image_format=image_format,
    )


def extend_image_margins(
    image: bytes,
    *,
    left: int,
    top: int,
    right: int,
    bottom: int,
    prompt: str,
    provider_name: ProviderName = "openai",
    image_format: str = "png",
    model: str | None = None,
) -> bytes:
    """Extend with explicit per-side pixel margins (uniform zoom-out uses equal margins)."""
    if provider_name == "gemini":
        from game_images.gemini_edit import extend_image_gemini_margins

        return extend_image_gemini_margins(
            image,
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            prompt=prompt,
            model=model,
        )
    if provider_name == "minimax":
        raise ValueError(
            "MiniMax does not support Extend. Choose OpenAI, Gemini, or Fal."
        )
    provider = get_provider(provider_name, model=model)  # type: ignore[arg-type]
    return provider.extend_margins(
        image,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        prompt=prompt,
        image_format=image_format,
    )


ZoomMode = Literal["in", "out"]
_MAX_ZOOM_MARGIN = 700


def _zoom_out_margins(width: int, height: int, factor: float) -> tuple[int, int, int, int]:
    if factor <= 1.0:
        raise ValueError("zoom out factor must be greater than 1 (e.g. 1.25 = 25% larger canvas)")
    left = int(round(width * (factor - 1) / 2))
    top = int(round(height * (factor - 1) / 2))
    right = left
    bottom = top
    return (
        min(_MAX_ZOOM_MARGIN, left),
        min(_MAX_ZOOM_MARGIN, top),
        min(_MAX_ZOOM_MARGIN, right),
        min(_MAX_ZOOM_MARGIN, bottom),
    )


def zoom_image(
    image: bytes,
    mode: ZoomMode,
    *,
    factor: float = 1.5,
    center_x: float = 0.5,
    center_y: float = 0.5,
    enhance: bool = False,
    prompt: str = "",
    provider_name: ProviderName = "openai",
    image_format: str = "png",
    model: str | None = None,
) -> bytes:
    """Zoom out (outpaint) or zoom in (crop, optional AI enhance)."""
    img = Image.open(io.BytesIO(image))
    w, h = img.size

    if mode == "out":
        left, top, right, bottom = _zoom_out_margins(w, h, factor)
        if left == top == right == bottom == 0:
            return image
        out_prompt = (
            prompt.strip()
            or "Seamlessly continue the scene in all directions. Match style, lighting, and perspective."
        )
        return extend_image_margins(
            image,
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            prompt=out_prompt,
            provider_name=provider_name,
            image_format=image_format,
            model=model,
        )

    if factor <= 1.0:
        raise ValueError("zoom in factor must be greater than 1 (e.g. 2 = keep center 50% of frame)")
    crop_w = max(1, int(round(w / factor)))
    crop_h = max(1, int(round(h / factor)))
    cx = max(0.0, min(1.0, center_x))
    cy = max(0.0, min(1.0, center_y))
    center_px = int(round(cx * w))
    center_py = int(round(cy * h))
    left = max(0, min(w - crop_w, center_px - crop_w // 2))
    top = max(0, min(h - crop_h, center_py - crop_h // 2))
    cropped = _crop_image(image, left=left, top=top, width=crop_w, height=crop_h)
    if not enhance:
        return cropped
    enhance_prompt = prompt.strip() or (
        "Enhance detail and clarity while keeping the same composition, style, colors, and subject."
    )
    return manipulate_image(
        cropped,
        enhance_prompt,
        provider_name=provider_name,
        image_format=image_format,
        model=model,
    )


def manipulate_image(
    image: bytes,
    prompt: str,
    provider_name: ProviderName = "openai",
    *,
    mask: bytes | None = None,
    image_format: str = "png",
    model: str | None = None,
) -> bytes:
    """Edit the image (or masked region) according to the prompt. Returns image bytes."""
    if provider_name == "gemini":
        from game_images.gemini_edit import manipulate_image_gemini

        return manipulate_image_gemini(image, prompt, mask=mask, model=model)
    if provider_name == "minimax":
        raise ValueError(
            "MiniMax does not support Manipulate. Choose OpenAI, Gemini, or Fal."
        )
    provider = get_provider(provider_name, model=model)  # type: ignore[arg-type]
    return provider.manipulate(
        image,
        prompt,
        mask=mask,
        image_format=image_format,
    )


def create_image(
    prompt: str,
    width: int,
    height: int,
    provider_name: ProviderName = "openai",
    *,
    model: str | None = None,
) -> bytes:
    return _create_image(prompt, width, height, provider_name, model=model)


def adjust_image(
    image: bytes,
    *,
    brightness: float = 1.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    sharpness: float = 1.0,
    blur_radius: float = 0.0,
    rotate_degrees: float = 0.0,
    flip: str = "none",
    resize_scale: float = 1.0,
    resize_width: int = 0,
    resize_height: int = 0,
    resize_keep_aspect: bool = True,
) -> bytes:
    from game_images.image_ops import FlipMode

    flip_mode: FlipMode = flip if flip in ("none", "x", "y", "xy") else "none"  # type: ignore[assignment]
    return _adjust_image(
        image,
        brightness=brightness,
        contrast=contrast,
        saturation=saturation,
        sharpness=sharpness,
        blur_radius=blur_radius,
        rotate_degrees=rotate_degrees,
        flip=flip_mode,
        resize_scale=resize_scale,
        resize_width=resize_width,
        resize_height=resize_height,
        resize_keep_aspect=resize_keep_aspect,
    )


def tile_image(image: bytes, mode: str) -> bytes:
    from game_images.image_ops import TileMode

    if mode not in (
        "offset_x",
        "offset_y",
        "offset_xy",
        "mirror_x",
        "mirror_y",
        "mirror_xy",
        "preview_2x2",
    ):
        raise ValueError(f"Unknown tile mode: {mode}")
    return _tile_image(image, mode)  # type: ignore[arg-type]


def generate_texture_map(image: bytes, map_type: str, *, strength: float = 1.0) -> bytes:
    from game_images.texture_maps import MapType

    allowed = ("bump", "normal", "roughness", "ao", "height")
    if map_type not in allowed:
        raise ValueError(f"map_type must be one of: {', '.join(allowed)}")
    return _generate_texture_map(image, map_type, strength=strength)  # type: ignore[arg-type]
