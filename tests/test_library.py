"""Tests for image library storage and rename."""

import io
from pathlib import Path

from PIL import Image

from game_images.library import Library, sanitize_filename


def _tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(128, 64, 32)).save(buf, format="PNG")
    return buf.getvalue()


def test_sanitize_filename_strips_paths() -> None:
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("/tmp/foo.png") == "foo.png"


def test_sanitize_filename_empty_becomes_untitled() -> None:
    assert sanitize_filename("") == "untitled.png"
    assert sanitize_filename("   ") == "untitled.png"


def test_sanitize_filename_removes_invalid_chars() -> None:
    assert sanitize_filename('bad<>name.png') == "badname.png"


def test_library_rename(tmp_path: Path) -> None:
    lib = Library(root=tmp_path)
    img_id = lib.add_image(_tiny_png(), "original.png", "image")
    assert lib.rename(img_id, "renamed-texture.png") is True
    meta = lib.get_metadata(img_id)
    assert meta is not None
    assert meta["filename"] == "renamed-texture.png"
