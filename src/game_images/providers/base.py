"""Provider protocol for image extend and manipulate operations."""

from typing import Literal, Protocol

Direction = Literal["north", "south", "east", "west"]


class Provider(Protocol):
    """Protocol for AI image extend (outpaint) and manipulate (inpaint) backends."""

    def extend(
        self,
        image: bytes,
        directions: list[Direction],
        amount_px: int,
        prompt: str,
        *,
        image_format: str = "png",
    ) -> bytes:
        """Extend the image in the given direction(s). Returns image bytes."""
        ...

    def manipulate(
        self,
        image: bytes,
        prompt: str,
        *,
        mask: bytes | None = None,
        image_format: str = "png",
    ) -> bytes:
        """Edit the image (or masked region) according to the prompt. Returns image bytes."""
        ...
