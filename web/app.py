"""FastAPI web UI for game-images: extend and manipulate."""

import io
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from PIL import Image

app = FastAPI(title="Game Images AI")

_library = None


def _get_library():
    global _library
    if _library is None:
        from game_images.library import Library
        _library = Library()
    return _library


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    """Ensure 500 responses include a JSON body with the error message for the client."""
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "Internal server error"},
    )


def normalize_upload_to_png(image_bytes: bytes) -> bytes:
    """Convert uploaded image (JPEG/WebP/etc.) to PNG bytes so providers get image/png."""
    buf = io.BytesIO(image_bytes)
    img = Image.open(buf)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()

# Import after app so we can run from project root with uvicorn web.app:app
def _core():
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
    return (
        extend_image,
        manipulate_image,
        shift_image,
        Direction,
        create_image,
        adjust_image,
        tile_image,
        generate_texture_map,
    )


def _parse_directions(s: str) -> list[str]:
    allowed = {"north", "south", "east", "west"}
    parts = [p.strip().lower() for p in (s or "north").split(",") if p.strip()]
    for p in parts:
        if p not in allowed:
            return ["north"]
    return parts if parts else ["north"]


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    p = Path(__file__).parent / "index.html"
    return p.read_text()


def _handle_provider_error(e: Exception) -> tuple[int, str]:
    """Map provider/core exceptions to HTTP status and user-facing message."""
    if isinstance(e, ValueError):
        return 400, str(e)
    # OpenAI / Fal API and network errors
    err_name = type(e).__name__
    if "openai" in type(e).__module__.lower() or "fal" in type(e).__module__.lower():
        return 502, f"Provider API error: {e!s}"
    if isinstance(e, (RuntimeError, OSError)):
        return 502, str(e)
    return 500, f"Unexpected error: {e!s}"


@app.post("/shift")
async def api_shift(
    image: UploadFile = File(...),
    direction: str = Form("west"),
    amount: str = Form("128"),
) -> Response:
    """Shift the image in the given direction; new area is black. Use before extend to fill the blank."""
    try:
        _, _, shift_image_fn, _, _, _, _, _ = _core()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not load app: {e!s}")
    direction = (direction or "west").strip().lower()
    if direction not in ("north", "south", "east", "west"):
        raise HTTPException(status_code=400, detail="Direction must be north, south, east, or west.")
    try:
        amount_int = int(amount)
    except (TypeError, ValueError):
        amount_int = 128
    if amount_int < 1 or amount_int > 2000:
        amount_int = min(max(amount_int, 1), 2000)
    try:
        body = await image.read()
        if not body:
            raise HTTPException(status_code=400, detail="No image data received.")
        body = normalize_upload_to_png(body)
        result = shift_image_fn(body, direction, amount_int)
    except HTTPException:
        raise
    except Exception as e:
        status, detail = _handle_provider_error(e)
        raise HTTPException(status_code=status, detail=detail)
    return Response(content=result, media_type="image/png")


@app.post("/extend")
async def api_extend(
    image: UploadFile = File(...),
    direction: str = Form("north"),
    amount: int = Form(128),
    prompt: str = Form(""),
    provider: str = Form("openai"),
    model: str | None = Form(None),
) -> Response:
    extend_image_fn, _, _, _, _, _, _, _ = _core()
    directions_list = _parse_directions(direction)
    prompt_text = prompt or "Seamlessly extend the image in the new area."
    try:
        body = await image.read()
        body = normalize_upload_to_png(body)
        result = extend_image_fn(
            body,
            directions_list,
            amount,
            prompt_text,
            provider_name=provider.lower(),
            model=model or None,
        )
    except Exception as e:
        status, detail = _handle_provider_error(e)
        raise HTTPException(status_code=status, detail=detail)
    return Response(content=result, media_type="image/png")


@app.post("/manipulate")
async def api_manipulate(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    mask: UploadFile | None = File(None),
    provider: str = Form("openai"),
    model: str | None = Form(None),
) -> Response:
    _, manipulate_image_fn, _, _, _, _, _, _ = _core()
    image_bytes = normalize_upload_to_png(await image.read())
    mask_bytes = await mask.read() if mask else None
    if mask_bytes:
        mask_bytes = normalize_upload_to_png(mask_bytes)
    try:
        result = manipulate_image_fn(
            image_bytes,
            prompt,
            provider_name=provider.lower(),
            mask=mask_bytes,
            model=model or None,
        )
    except Exception as e:
        status, detail = _handle_provider_error(e)
        raise HTTPException(status_code=status, detail=detail)
    return Response(content=result, media_type="image/png")


@app.post("/create")
async def api_create(
    prompt: str = Form(...),
    width: int = Form(1024),
    height: int = Form(1024),
    provider: str = Form("openai"),
    model: str | None = Form(None),
) -> Response:
    _, _, _, _, create_image_fn, _, _, _ = _core()
    w = max(64, min(2048, width))
    h = max(64, min(2048, height))
    try:
        result = create_image_fn(
            prompt,
            w,
            h,
            provider_name=provider.lower(),  # type: ignore[arg-type]
            model=model or None,
        )
    except Exception as e:
        status, detail = _handle_provider_error(e)
        raise HTTPException(status_code=status, detail=detail)
    return Response(content=result, media_type="image/png")


@app.post("/adjust")
async def api_adjust(
    image: UploadFile = File(...),
    brightness: float = Form(1.0),
    contrast: float = Form(1.0),
    saturation: float = Form(1.0),
    sharpness: float = Form(1.0),
    blur_radius: float = Form(0.0),
    rotate_degrees: float = Form(0.0),
    flip: str = Form("none"),
) -> Response:
    _, _, _, _, _, adjust_image_fn, _, _ = _core()
    try:
        body = normalize_upload_to_png(await image.read())
        result = adjust_image_fn(
            body,
            brightness=brightness,
            contrast=contrast,
            saturation=saturation,
            sharpness=sharpness,
            blur_radius=blur_radius,
            rotate_degrees=rotate_degrees,
            flip=flip,
        )
    except Exception as e:
        status, detail = _handle_provider_error(e)
        raise HTTPException(status_code=status, detail=detail)
    return Response(content=result, media_type="image/png")


@app.post("/tile")
async def api_tile(
    image: UploadFile = File(...),
    mode: str = Form("offset_x"),
) -> Response:
    _, _, _, _, _, _, tile_image_fn, _ = _core()
    try:
        body = normalize_upload_to_png(await image.read())
        result = tile_image_fn(body, mode)
    except Exception as e:
        status, detail = _handle_provider_error(e)
        raise HTTPException(status_code=status, detail=detail)
    return Response(content=result, media_type="image/png")


@app.post("/maps")
async def api_maps(
    image: UploadFile = File(...),
    map_type: str = Form("bump"),
    strength: float = Form(1.0),
) -> Response:
    _, _, _, _, _, _, _, generate_texture_map_fn = _core()
    try:
        body = normalize_upload_to_png(await image.read())
        result = generate_texture_map_fn(body, map_type, strength=strength)
    except Exception as e:
        status, detail = _handle_provider_error(e)
        raise HTTPException(status_code=status, detail=detail)
    return Response(content=result, media_type="image/png")


@app.get("/library")
async def library_list(
    type: str | None = Query(None, description="Filter by type: image, mask, result (comma-separated for multiple)"),
    tag: str | None = Query(None),
) -> list:
    """List images in the library."""
    lib = _get_library()
    return lib.list_images(type=type, tag=tag)


@app.post("/library/import")
async def library_import(
    image: UploadFile = File(...),
    type: str = Form("image"),
) -> dict:
    """Import an image into the library."""
    if type not in ("image", "mask", "result"):
        raise HTTPException(status_code=400, detail="type must be image, mask, or result")
    body = await image.read()
    if not body:
        raise HTTPException(status_code=400, detail="No image data received.")
    png_bytes = normalize_upload_to_png(body)
    filename = image.filename or "imported.png"
    lib = _get_library()
    img_id = lib.add_image(png_bytes, filename, type)
    meta = lib.get_metadata(img_id)
    return {"id": img_id, "metadata": meta}


@app.get("/library/{img_id}")
async def library_get(img_id: str) -> Response:
    """Serve image file by id."""
    lib = _get_library()
    data = lib.get_image(img_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(content=data, media_type="image/png")


@app.get("/library/{img_id}/meta")
async def library_get_meta(img_id: str) -> dict:
    """Get metadata by id."""
    lib = _get_library()
    meta = lib.get_metadata(img_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return meta


@app.patch("/library/{img_id}")
async def library_update(img_id: str, body: dict = Body(...)) -> dict:
    """Update metadata."""
    lib = _get_library()
    if not lib.get_metadata(img_id):
        raise HTTPException(status_code=404, detail="Image not found")
    lib.update_metadata(img_id, **{k: v for k, v in body.items() if v is not None})
    return lib.get_metadata(img_id) or {}


@app.delete("/library/{img_id}")
async def library_delete(img_id: str) -> dict:
    """Remove image from library."""
    lib = _get_library()
    if not lib.delete(img_id):
        raise HTTPException(status_code=404, detail="Image not found")
    return {"deleted": img_id}


@app.post("/library/from-result")
async def library_from_result(
    image: UploadFile = File(...),
    prompt: str = Form(""),
    source_id: str | None = Form(None),
    mask_id: str | None = Form(None),
) -> dict:
    """Add a generated result to the library."""
    body = await image.read()
    if not body:
        raise HTTPException(status_code=400, detail="No image data received.")
    png_bytes = normalize_upload_to_png(body)
    lib = _get_library()
    img_id = lib.add_image(
        png_bytes,
        "result.png",
        "result",
        prompt=prompt or None,
        source_id=source_id or None,
        mask_id=mask_id or None,
    )
    meta = lib.get_metadata(img_id)
    return {"id": img_id, "metadata": meta}


class KeysUpdateBody(BaseModel):
    """Update stored API keys. Omit a field to leave it unchanged; use empty string to remove."""

    openai_api_key: str | None = None
    fal_api_key: str | None = None


@app.get("/settings/keys")
async def settings_keys_get() -> dict:
    from game_images.settings import keys_status

    return keys_status()


@app.put("/settings/keys")
async def settings_keys_put(body: KeysUpdateBody) -> dict:
    from game_images.settings import update_keys

    return update_keys(
        openai_api_key=body.openai_api_key,
        fal_api_key=body.fal_api_key,
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": "game-images"}
