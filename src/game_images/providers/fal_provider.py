"""Fal.ai provider: outpaint for extend, Gemini 2.5 Flash Image for manipulate."""

import io
import os
import tempfile
import urllib.request
from typing import get_args

from game_images.providers.base import Direction

DirectionTuple = tuple[int, int, int, int]  # left, top, right, bottom


def _directions_to_expand(
    directions: list[Direction],
    amount_px: int,
) -> DirectionTuple:
    direction_set = set(directions)
    return (
        amount_px if "west" in direction_set else 0,
        amount_px if "north" in direction_set else 0,
        amount_px if "east" in direction_set else 0,
        amount_px if "south" in direction_set else 0,
    )


def _download_url(url: str) -> bytes:
    with urllib.request.urlopen(url) as r:
        return r.read()


class FalProvider:
    """Provider using Fal.ai: outpaint for extend, Gemini edit for manipulate."""

    OUTPAINT_APP = "fal-ai/image-apps-v2/outpaint"
    GEMINI_EDIT_APP = "fal-ai/gemini-25-flash-image/edit"

    def __init__(self, *, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("FAL_KEY")
        if not self._api_key:
            raise ValueError(
                "Fal API key not set. Add it in Settings (gear icon) or set FAL_KEY."
            )

    def _upload_image(self, image: bytes, suffix: str = ".png") -> str:
        import fal_client
        with tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False
        ) as f:
            f.write(image)
            path = f.name
        try:
            return fal_client.upload_file(path)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def extend_margins(
        self,
        image: bytes,
        *,
        left: int,
        top: int,
        right: int,
        bottom: int,
        prompt: str,
        image_format: str = "png",
    ) -> bytes:
        if left == top == right == bottom == 0:
            return image
        import fal_client

        image_url = self._upload_image(image)
        inp = {
            "image_url": image_url,
            "expand_left": min(700, left),
            "expand_right": min(700, right),
            "expand_top": min(700, top),
            "expand_bottom": min(700, bottom),
            "prompt": prompt or "",
        }
        result = fal_client.run(self.OUTPAINT_APP, arguments=inp)
        images = result.get("images") or []
        if not images:
            raise RuntimeError("Fal outpaint returned no images")
        url = images[0].get("url")
        if not url:
            raise RuntimeError("Fal outpaint image had no url")
        return _download_url(url)

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
        return self.extend_margins(
            image,
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            prompt=prompt,
            image_format=image_format,
        )

    def manipulate(
        self,
        image: bytes,
        prompt: str,
        *,
        mask: bytes | None = None,
        image_format: str = "png",
    ) -> bytes:
        import fal_client
        image_url = self._upload_image(image)
        inp = {
            "prompt": prompt,
            "image_urls": [image_url],
        }
        if mask is not None:
            mask_url = self._upload_image(mask)
            inp["image_urls"].append(mask_url)
        result = fal_client.run(self.GEMINI_EDIT_APP, arguments=inp)
        images = result.get("images") or []
        if not images:
            raise RuntimeError("Fal Gemini edit returned no images")
        url = images[0].get("url")
        if not url:
            raise RuntimeError("Fal edit image had no url")
        return _download_url(url)
