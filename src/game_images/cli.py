"""CLI for game-images: extend and manipulate subcommands."""

from pathlib import Path

import typer

from game_images.core import (
    adjust_image,
    create_image,
    extend_image,
    generate_texture_map,
    manipulate_image,
    shift_image,
    tile_image,
)
from game_images.providers.base import Direction

app = typer.Typer(
    help="Create and edit game images: AI generate/extend/inpaint, adjust, tile, and texture maps.",
)


def _parse_directions(s: str) -> list[Direction]:
    allowed = {"north", "south", "east", "west"}
    parts = [p.strip().lower() for p in s.split(",") if p.strip()]
    for p in parts:
        if p not in allowed:
            raise typer.BadParameter(f"Direction must be one or more of: north, south, east, west (comma-separated). Got: {p}")
    return list(parts)


@app.command("create")
def create_cmd(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Text-to-image prompt."),
    width: int = typer.Option(1024, "--width", "-W", min=64, max=2048),
    height: int = typer.Option(1024, "--height", "-H", min=64, max=2048),
    provider: str = typer.Option("openai", "--provider", help="openai or fal."),
    model: str | None = typer.Option(None, "--model", help="OpenAI model (e.g. dall-e-3)."),
    output: Path = typer.Option(..., "--output", "-o", path_type=Path),
) -> None:
    """Generate a new image from a prompt."""
    try:
        result = create_image(
            prompt,
            width,
            height,
            provider_name=provider.lower(),  # type: ignore[arg-type]
            model=model,
        )
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    typer.echo(f"Wrote {output}")


@app.command()
def adjust(
    image: Path = typer.Argument(..., path_type=Path, exists=True),
    brightness: float = typer.Option(1.0, "--brightness"),
    contrast: float = typer.Option(1.0, "--contrast"),
    saturation: float = typer.Option(1.0, "--saturation"),
    sharpness: float = typer.Option(1.0, "--sharpness"),
    blur: float = typer.Option(0.0, "--blur", help="Gaussian blur radius."),
    rotate: float = typer.Option(0.0, "--rotate", help="Degrees."),
    flip: str = typer.Option("none", "--flip", help="none, x, y, or xy."),
    resize_scale: float = typer.Option(
        1.0, "--resize-scale", help="Uniform scale (1.0 = unchanged). Used if not 1.0."
    ),
    width: int = typer.Option(0, "--width", help="Target width in px (0 = ignore)."),
    height: int = typer.Option(0, "--height", help="Target height in px (0 = ignore)."),
    stretch: bool = typer.Option(
        False, "--stretch", help="Stretch to exact width×height instead of fitting within."
    ),
    output: Path = typer.Option(..., "--output", "-o", path_type=Path),
) -> None:
    """Traditional brightness/contrast/saturation and transforms."""
    result = adjust_image(
        image.read_bytes(),
        brightness=brightness,
        contrast=contrast,
        saturation=saturation,
        sharpness=sharpness,
        blur_radius=blur,
        rotate_degrees=rotate,
        flip=flip,
        resize_scale=resize_scale,
        resize_width=width,
        resize_height=height,
        resize_keep_aspect=not stretch,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    typer.echo(f"Wrote {output}")


@app.command()
def tile(
    image: Path = typer.Argument(..., path_type=Path, exists=True),
    mode: str = typer.Option(
        "offset_x",
        "--mode",
        "-m",
        help="offset_x|offset_y|offset_xy|mirror_x|mirror_y|mirror_xy|preview_2x2",
    ),
    output: Path = typer.Option(..., "--output", "-o", path_type=Path),
) -> None:
    """Seamless tiling helpers (offset swap or mirror)."""
    try:
        result = tile_image(image.read_bytes(), mode)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    typer.echo(f"Wrote {output}")


@app.command("maps")
def maps_cmd(
    image: Path = typer.Argument(..., path_type=Path, exists=True),
    map_type: str = typer.Option("bump", "--type", "-t", help="bump|normal|roughness|ao|height"),
    strength: float = typer.Option(1.0, "--strength"),
    output: Path = typer.Option(..., "--output", "-o", path_type=Path),
) -> None:
    """Generate a companion texture map from a base image."""
    try:
        result = generate_texture_map(image.read_bytes(), map_type, strength=strength)
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    typer.echo(f"Wrote {output}")


@app.command()
def shift(
    image: Path = typer.Argument(..., help="Path to the image.", path_type=Path, exists=True),
    direction: str = typer.Option(
        "west",
        "--direction",
        "-d",
        help="Direction to shift: north, south, east, west (content moves this way; blank appears opposite).",
    ),
    amount: int = typer.Option(
        128,
        "--amount",
        "-a",
        help="Pixels to shift (and size of blank area).",
        min=1,
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        path_type=Path,
        help="Output image path.",
    ),
) -> None:
    """Shift the image in a direction; new area is black. Then use extend to fill the blank."""
    direction = direction.strip().lower()
    if direction not in ("north", "south", "east", "west"):
        raise typer.BadParameter("Direction must be north, south, east, or west.")
    image_bytes = image.read_bytes()
    result = shift_image(image_bytes, direction, amount)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    typer.echo(f"Wrote {output}")


@app.command()
def extend(
    image: Path = typer.Argument(..., help="Path to the base image.", path_type=Path, exists=True),
    direction: str = typer.Option(
        "north",
        "--direction",
        "-d",
        help="Direction(s) to extend: north, south, east, west (comma-separated).",
    ),
    amount: int = typer.Option(
        128,
        "--amount",
        "-a",
        help="Number of pixels to add in each chosen direction.",
        min=1,
        max=700,
    ),
    prompt: str = typer.Option(
        "",
        "--prompt",
        "-p",
        help="Prompt to guide the outpainting (e.g. 'seamless sky and trees').",
    ),
    provider: str = typer.Option(
        "openai",
        "--provider",
        help="AI provider: openai or fal.",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        path_type=Path,
        help="Output image path.",
    ),
) -> None:
    """Extend the image in the given direction(s) (outpainting)."""
    directions_list = _parse_directions(direction)
    prompt_text = prompt or "Seamlessly extend the image in the new area."
    image_bytes = image.read_bytes()
    try:
        result = extend_image(
            image_bytes,
            directions_list,
            amount,
            prompt_text,
            provider_name=provider.lower(),
        )
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    typer.echo(f"Wrote {output}")


@app.command()
def manipulate(
    image: Path = typer.Argument(..., help="Path to the base image.", path_type=Path, exists=True),
    prompt: str = typer.Option(..., "--prompt", "-p", help="Edit instruction (e.g. 'add a red hat')."),
    mask: Path | None = typer.Option(
        None,
        "--mask",
        "-m",
        path_type=Path,
        exists=True,
        help="Optional mask image (PNG; transparent = area to edit).",
    ),
    provider: str = typer.Option(
        "openai",
        "--provider",
        help="AI provider: openai or fal.",
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        path_type=Path,
        help="Output image path.",
    ),
) -> None:
    """Edit the image (or masked region) according to the prompt (inpainting)."""
    image_bytes = image.read_bytes()
    mask_bytes = mask.read_bytes() if mask else None
    try:
        result = manipulate_image(
            image_bytes,
            prompt,
            provider_name=provider.lower(),
            mask=mask_bytes,
        )
    except ValueError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(1)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    typer.echo(f"Wrote {output}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind host."),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port."),
) -> None:
    """Run the web UI (FastAPI) locally."""
    import uvicorn
    from pathlib import Path
    # Run web.app so that game_images is importable (same package)
    web_dir = Path(__file__).resolve().parent.parent.parent / "web"
    if not (web_dir / "app.py").exists():
        typer.echo("Web app not found. Run from project root.", err=True)
        raise typer.Exit(1)
    # Add project root to path so "web.app" is loadable
    import sys
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    uvicorn.run("web.app:app", host=host, port=port, reload=False)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
