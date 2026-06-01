"""OpenAI Images API provider for extend and manipulate."""

import io
import os
from typing import get_args

from PIL import Image

from game_images.providers.base import Direction

DirectionTuple = tuple[int, int, int, int]  # expand_left, expand_top, expand_right, expand_bottom


def _directions_to_expand(
    directions: list[Direction],
    amount_px: int,
) -> DirectionTuple:
    """Convert direction list to (left, top, right, bottom) pixel expansion."""
    direction_set = set(directions)
    args = get_args(Direction)
    return (
        amount_px if "west" in direction_set else 0,
        amount_px if "north" in direction_set else 0,
        amount_px if "east" in direction_set else 0,
        amount_px if "south" in direction_set else 0,
    )


def _build_outpaint_canvas_and_mask(
    image: bytes,
    expand_left: int,
    expand_top: int,
    expand_right: int,
    expand_bottom: int,
) -> tuple[bytes, bytes]:
    """Build a larger canvas with the image placed and a PNG mask (transparent = fill)."""
    img = Image.open(io.BytesIO(image)).convert("RGBA")
    w, h = img.size
    new_w = w + expand_left + expand_right
    new_h = h + expand_top + expand_bottom
    canvas = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 255))
    canvas.paste(img, (expand_left, expand_top))
    mask = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 255))
    for y in range(new_h):
        for x in range(new_w):
            if (
                expand_left <= x < expand_left + w
                and expand_top <= y < expand_top + h
            ):
                mask.putpixel((x, y), (0, 0, 0, 255))
            else:
                mask.putpixel((x, y), (0, 0, 0, 0))
    buf_img = io.BytesIO()
    buf_mask = io.BytesIO()
    canvas.save(buf_img, format="PNG")
    mask.save(buf_mask, format="PNG")
    return buf_img.getvalue(), buf_mask.getvalue()


class OpenAIProvider:
    """Provider using OpenAI Images API (edit endpoint) for extend and manipulate."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._model = (
            model or os.environ.get("OPENAI_IMAGE_MODEL") or "gpt-image-1.5"
        )
        if not self._api_key:
            raise ValueError(
                "OpenAI API key not set. Add it in Settings (gear icon) or set OPENAI_API_KEY."
            )

    def _client(self):
        from openai import OpenAI
        return OpenAI(api_key=self._api_key)

    def extend(
        self,
        image: bytes,
        directions: list[Direction],
        amount_px: int,
        prompt: str,
        *,
        image_format: str = "png",
    ) -> bytes:
        left, top, right, bottom = _directions_to_expand(directions, amount_px)
        if left == top == right == bottom == 0:
            return image
        canvas_bytes, mask_bytes = _build_outpaint_canvas_and_mask(
            image, left, top, right, bottom
        )
        edit_prompt = prompt or "Seamlessly extend the image in the new area."
        client = self._client()
        # Pass (filename, bytes, content_type) so the API receives image/png, not application/octet-stream
        image_file = ("image.png", canvas_bytes, "image/png")
        mask_file = ("mask.png", mask_bytes, "image/png")
        resp = client.images.edit(
            model=self._model,
            image=image_file,
            mask=mask_file,
            prompt=edit_prompt,
            n=1,
            size="auto",
        )
        if not resp.data:
            raise RuntimeError("OpenAI edit returned no image")
        first = resp.data[0]
        if getattr(first, "b64_json", None):
            import base64
            return base64.b64decode(first.b64_json)
        if getattr(first, "url", None):
            import urllib.request
            with urllib.request.urlopen(first.url) as r:
                return r.read()
        raise RuntimeError("OpenAI response had no b64_json or url")

    def manipulate(
        self,
        image: bytes,
        prompt: str,
        *,
        mask: bytes | None = None,
        image_format: str = "png",
    ) -> bytes:
        client = self._client()
        image_file = ("image.png", image, "image/png")
        kwargs = {
            "model": self._model,
            "image": image_file,
            "prompt": prompt,
            "n": 1,
            "size": "auto",
        }
        if mask is not None:
            kwargs["mask"] = ("mask.png", mask, "image/png")
        resp = client.images.edit(**kwargs)
        if not resp.data:
            raise RuntimeError("OpenAI edit returned no image")
        first = resp.data[0]
        if getattr(first, "b64_json", None):
            import base64
            return base64.b64decode(first.b64_json)
        if getattr(first, "url", None):
            import urllib.request
            with urllib.request.urlopen(first.url) as r:
                return r.read()
        raise RuntimeError("OpenAI response had no b64_json or url")
