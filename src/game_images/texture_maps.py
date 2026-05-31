"""Procedural PBR-style maps derived from a base color texture."""

from __future__ import annotations

import io
from typing import Literal

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

MapType = Literal["bump", "normal", "roughness", "ao", "height"]


def _luminance(img: Image.Image) -> Image.Image:
    return img.convert("L")


def _to_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _normalize_normal(dx: Image.Image, dy: Image.Image) -> Image.Image:
    """Pack tangent-space normal into RGB (128,128,255 = flat)."""
    w, h = dx.size
    out = Image.new("RGB", (w, h))
    px_out = out.load()
    px_x = dx.load()
    px_y = dy.load()
    for y in range(h):
        for x in range(w):
            nx = (px_x[x, y] - 128) / 127.0
            ny = (px_y[x, y] - 128) / 127.0
            nz = max(0.0, 1.0 - min(1.0, (nx * nx + ny * ny) ** 0.5))
            r = int(128 + 127 * nx)
            g = int(128 + 127 * ny)
            b = int(255 * nz)
            px_out[x, y] = (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
    return out


def generate_texture_map(image: bytes, map_type: MapType, *, strength: float = 1.0) -> bytes:
    """Derive a grayscale or normal map from the base image."""
    base = Image.open(io.BytesIO(image)).convert("RGB")
    lum = _luminance(base)
    strength = max(0.1, min(4.0, strength))

    def _contrast(gray: Image.Image, factor: float) -> Image.Image:
        return ImageEnhance.Contrast(gray).enhance(factor)

    if map_type == "bump":
        edge = lum.filter(ImageFilter.FIND_EDGES)
        combined = Image.blend(lum, edge, 0.35)
        out = _contrast(combined, strength)
    elif map_type == "height":
        out = _contrast(lum, strength)
    elif map_type == "roughness":
        blurred = lum.filter(ImageFilter.GaussianBlur(radius=2))
        out = _contrast(ImageOps.invert(blurred), strength)
    elif map_type == "ao":
        dark = ImageOps.autocontrast(lum)
        out = _contrast(ImageOps.invert(dark), 0.5 + strength * 0.5)
    elif map_type == "normal":
        blurred = lum.filter(ImageFilter.GaussianBlur(radius=1))
        dx = ImageOps.invert(blurred).filter(ImageFilter.Kernel(
            (3, 3),
            [-1, 0, 1, -2, 0, 2, -1, 0, 1],
            scale=1,
            offset=128,
        ))
        dy = ImageOps.invert(blurred).filter(ImageFilter.Kernel(
            (3, 3),
            [-1, -2, -1, 0, 0, 0, 1, 2, 1],
            scale=1,
            offset=128,
        ))
        out = _normalize_normal(dx, dy)
        return _to_bytes(out)
    else:
        raise ValueError(f"Unknown map type: {map_type}")

    return _to_bytes(out.convert("L"))
