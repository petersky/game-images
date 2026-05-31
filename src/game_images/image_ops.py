"""Traditional image adjustments, transforms, and seamless tiling helpers."""

from __future__ import annotations

import io
from typing import Literal

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

TileMode = Literal[
    "offset_x",
    "offset_y",
    "offset_xy",
    "mirror_x",
    "mirror_y",
    "mirror_xy",
    "preview_2x2",
]
FlipMode = Literal["none", "x", "y", "xy"]


def _to_rgba(image: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(image))
    if img.mode in ("RGBA", "LA"):
        return img.convert("RGBA")
    return img.convert("RGB").convert("RGBA")


def _save_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def adjust_image(
    image: bytes,
    *,
    brightness: float = 1.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    sharpness: float = 1.0,
    blur_radius: float = 0.0,
    rotate_degrees: float = 0.0,
    flip: FlipMode = "none",
) -> bytes:
    """Apply Pillow-based adjustments. Factors of 1.0 leave that channel unchanged."""
    img = _to_rgba(image)
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if saturation != 1.0:
        img = ImageEnhance.Color(img).enhance(saturation)
    if sharpness != 1.0:
        img = ImageEnhance.Sharpness(img).enhance(sharpness)
    if blur_radius > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    if rotate_degrees % 360 != 0:
        img = img.rotate(rotate_degrees, expand=True, resample=Image.Resampling.BICUBIC)
    if flip == "x":
        img = ImageOps.mirror(img)
    elif flip == "y":
        img = ImageOps.flip(img)
    elif flip == "xy":
        img = ImageOps.flip(ImageOps.mirror(img))
    return _save_png(img)


def _offset_seam(img: Image.Image, axis: str) -> Image.Image:
    w, h = img.size
    out = img.copy()
    if axis in ("x", "xy"):
        half = w // 2
        if half > 0:
            left = out.crop((0, 0, half, h))
            right = out.crop((half, 0, w, h))
            canvas = Image.new("RGBA", (w, h))
            canvas.paste(right, (0, 0))
            canvas.paste(left, (half, 0))
            out = canvas
    if axis in ("y", "xy"):
        w, h = out.size
        half = h // 2
        if half > 0:
            top = out.crop((0, 0, w, half))
            bottom = out.crop((0, half, w, h))
            canvas = Image.new("RGBA", (w, h))
            canvas.paste(bottom, (0, 0))
            canvas.paste(top, (0, half))
            out = canvas
    return out


def _mirror_tile(img: Image.Image, axes: str) -> Image.Image:
    w, h = img.size
    if axes == "x":
        mirrored = ImageOps.mirror(img)
        out = Image.new("RGBA", (w * 2, h))
        out.paste(img, (0, 0))
        out.paste(mirrored, (w, 0))
        return out
    if axes == "y":
        flipped = ImageOps.flip(img)
        out = Image.new("RGBA", (w, h * 2))
        out.paste(img, (0, 0))
        out.paste(flipped, (0, h))
        return out
    mx = ImageOps.mirror(img)
    my = ImageOps.flip(img)
    mxy = ImageOps.flip(ImageOps.mirror(img))
    out = Image.new("RGBA", (w * 2, h * 2))
    out.paste(img, (0, 0))
    out.paste(mx, (w, 0))
    out.paste(my, (0, h))
    out.paste(mxy, (w, h))
    return out


def tile_image(image: bytes, mode: TileMode) -> bytes:
    """Prepare or preview seamless tiling."""
    img = _to_rgba(image)
    if mode == "offset_x":
        out = _offset_seam(img, "x")
    elif mode == "offset_y":
        out = _offset_seam(img, "y")
    elif mode == "offset_xy":
        out = _offset_seam(img, "xy")
    elif mode == "mirror_x":
        out = _mirror_tile(img, "x")
    elif mode == "mirror_y":
        out = _mirror_tile(img, "y")
    elif mode == "mirror_xy":
        out = _mirror_tile(img, "xy")
    elif mode == "preview_2x2":
        out = Image.new("RGBA", (img.width * 2, img.height * 2))
        for oy in range(2):
            for ox in range(2):
                tile = img
                if ox == 1:
                    tile = ImageOps.mirror(tile)
                if oy == 1:
                    tile = ImageOps.flip(tile)
                out.paste(tile, (ox * img.width, oy * img.height))
    else:
        raise ValueError(f"Unknown tile mode: {mode}")
    return _save_png(out)
