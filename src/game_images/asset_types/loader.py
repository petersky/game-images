"""Load third-party asset types from setuptools entry points."""

from __future__ import annotations

import logging
from typing import Callable, Iterable, Protocol

from game_images.asset_types.base import AssetTypeRegistry

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "game_images.asset_types"


class _EntryPoint(Protocol):
    name: str

    def load(self) -> Callable[[AssetTypeRegistry], None]: ...


def _iter_entry_points() -> Iterable[_EntryPoint]:
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover
        return []

    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        eps = entry_points().get(ENTRY_POINT_GROUP, [])
    return eps


def load_entry_point_types(
    registry: AssetTypeRegistry,
    *,
    entry_points: Iterable[_EntryPoint] | None = None,
) -> list[str]:
    """Register asset types from entry points. Returns loaded entry names."""
    loaded: list[str] = []
    for ep in entry_points if entry_points is not None else _iter_entry_points():
        try:
            register_fn = ep.load()
            register_fn(registry)
            loaded.append(ep.name)
        except Exception:
            logger.exception("Failed to load asset type entry point %r", ep.name)
    return loaded
