"""Built-in asset type registrations."""

from __future__ import annotations

from game_images.asset_types.base import AssetTypeDefinition, AssetTypeRegistry, AssetTypeUI

_IMAGE_BASE = frozenset(
    {
        "image.preview",
        "image.adjust",
        "image.tile",
        "image.prepare",
        "image.zoom",
        "image.extend",
        "image.manipulate",
    }
)

_TEXTURE_EXTRA = frozenset(
    {
        "texture.maps",
        "texture.seamless",
        "texture.derivatives",
    }
)

_SKYDOME_EXTRA = frozenset(
    {
        "skydome.preview",
        "skydome.lightmap",
    }
)


def register_builtin_types(registry: AssetTypeRegistry) -> None:
    registry.register(
        AssetTypeDefinition(
            id="generic_image",
            label="Image",
            description="General-purpose image asset.",
            capabilities=_IMAGE_BASE,
        )
    )
    registry.register(
        AssetTypeDefinition(
            id="texture",
            label="Texture",
            description="Tileable surfaces with maps and seamless tooling.",
            extends="generic_image",
            capabilities=_TEXTURE_EXTRA,
            default_filename_suffix="_albedo",
            ui=AssetTypeUI(
                preview_modes=("flat", "seamless_2x2"),
                workflow_ids=("tileable",),
            ),
        )
    )
    registry.register(
        AssetTypeDefinition(
            id="skydome",
            label="Skydome",
            description="Environment sky / cubemap-style backdrop.",
            extends="generic_image",
            capabilities=_SKYDOME_EXTRA,
            default_filename_suffix="_skydome",
            ui=AssetTypeUI(
                preview_modes=("flat", "equirectangular"),
                workflow_ids=("environment",),
            ),
        )
    )
    registry.register(
        AssetTypeDefinition(
            id="background",
            label="Background",
            description="Scene backdrop or matte painting.",
            extends="generic_image",
            capabilities=frozenset(),
            ui=AssetTypeUI(workflow_ids=("environment",)),
        )
    )
