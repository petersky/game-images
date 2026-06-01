"""Unit tests for local image ops (no API keys)."""

import io

from PIL import Image

from game_images.core import adjust_image, generate_texture_map, tile_image


def _rgb_png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color=(10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def test_adjust_resize_scale() -> None:
    raw = _rgb_png(200, 100)
    out = adjust_image(raw, resize_scale=0.5)
    img = Image.open(io.BytesIO(out))
    assert img.size == (100, 50)


def test_adjust_resize_fit_within() -> None:
    raw = _rgb_png(400, 200)
    out = adjust_image(raw, resize_width=100, resize_height=100, resize_keep_aspect=True)
    img = Image.open(io.BytesIO(out))
    assert img.size == (100, 50)


def test_adjust_resize_stretch() -> None:
    raw = _rgb_png(400, 200)
    out = adjust_image(
        raw, resize_width=64, resize_height=32, resize_keep_aspect=False, resize_scale=1.0
    )
    img = Image.open(io.BytesIO(out))
    assert img.size == (64, 32)


def test_adjust_and_tile_roundtrip() -> None:
    from PIL import Image
    import io

    img = Image.new("RGB", (64, 64), color=(100, 120, 140))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()

    adjusted = adjust_image(raw, brightness=1.1, contrast=0.9)
    assert len(adjusted) > 100

    tiled = tile_image(raw, "offset_x")
    assert len(tiled) > 100


def test_generate_bump_map() -> None:
    from PIL import Image
    import io

    img = Image.new("RGB", (32, 32), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    bump = generate_texture_map(buf.getvalue(), "bump")
    assert bump[:8] == b"\x89PNG\r\n\x1a\n"
