"""Unit tests for local image ops (no API keys)."""

from game_images.core import adjust_image, generate_texture_map, tile_image


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
