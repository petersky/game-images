"""Tests for zoom helpers (no API)."""

import io

from PIL import Image

from game_images.core import _zoom_out_margins
from game_images.image_ops import crop_image


def _rgb_png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=(40, 80, 120)).save(buf, format="PNG")
    return buf.getvalue()


def test_zoom_out_margins_uniform() -> None:
    left, top, right, bottom = _zoom_out_margins(400, 200, 1.5)
    assert left == 100 and right == 100
    assert top == 50 and bottom == 50


def test_crop_image_center() -> None:
    raw = _rgb_png(200, 100)
    out = crop_image(raw, left=50, top=25, width=100, height=50)
    img = Image.open(io.BytesIO(out))
    assert img.size == (100, 50)
