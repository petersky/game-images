"""FastAPI web UI for game-images: extend and manipulate."""

import io
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel
from PIL import Image

app = FastAPI(title="Game Images AI")

_library = None
_projects = None


def _get_library():
    global _library
    if _library is None:
        from game_images.library import Library
        _library = Library()
    return _library


def _get_projects():
    global _projects
    if _projects is None:
        from game_images.projects import ProjectStore
        _projects = ProjectStore()
    return _projects


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
        zoom_image,
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
        zoom_image,
    )


def _parse_directions(s: str) -> list[str]:
    allowed = {"north", "south", "east", "west", "all"}
    parts = [p.strip().lower() for p in (s or "north").split(",") if p.strip()]
    if len(parts) == 1 and parts[0] == "all":
        return ["north", "south", "east", "west"]
    for p in parts:
        if p not in allowed:
            return ["north"]
    return [p for p in parts if p != "all"] or ["north"]


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    p = Path(__file__).parent / "index.html"
    return p.read_text()


def _handle_provider_error(e: Exception) -> tuple[int, dict]:
    """Map provider/core exceptions to HTTP status and structured detail for the UI."""
    from game_images.api_errors import format_exception_for_http

    return format_exception_for_http(e)


@app.post("/shift")
async def api_shift(
    image: UploadFile = File(...),
    direction: str = Form("west"),
    amount: str = Form("128"),
) -> Response:
    """Shift the image in the given direction; new area is black. Use before extend to fill the blank."""
    try:
        _, _, shift_image_fn, _, _, _, _, _, _ = _core()
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
    extend_image_fn, _, _, _, _, _, _, _, _ = _core()
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


@app.post("/zoom")
async def api_zoom(
    image: UploadFile = File(...),
    mode: str = Form("out"),
    factor: float = Form(1.5),
    center_x: float = Form(0.5),
    center_y: float = Form(0.5),
    enhance: str = Form("false"),
    prompt: str = Form(""),
    provider: str = Form("openai"),
    model: str | None = Form(None),
) -> Response:
    _, _, _, _, _, _, _, _, zoom_image_fn = _core()
    zoom_mode = (mode or "out").strip().lower()
    if zoom_mode not in ("in", "out"):
        raise HTTPException(status_code=400, detail="mode must be in or out")
    try:
        factor_f = float(factor)
    except (TypeError, ValueError):
        factor_f = 1.5
    if factor_f < 1.05 or factor_f > 4.0:
        raise HTTPException(
            status_code=400,
            detail="factor must be between 1.05 and 4.0",
        )
    do_enhance = (enhance or "").strip().lower() in ("1", "true", "yes", "on")
    try:
        body = await image.read()
        body = normalize_upload_to_png(body)
        result = zoom_image_fn(
            body,
            zoom_mode,  # type: ignore[arg-type]
            factor=factor_f,
            center_x=float(center_x),
            center_y=float(center_y),
            enhance=do_enhance,
            prompt=prompt or "",
            provider_name=provider.lower(),  # type: ignore[arg-type]
            model=model or None,
        )
    except HTTPException:
        raise
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
    _, manipulate_image_fn, _, _, _, _, _, _, _ = _core()
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
    _, _, _, _, create_image_fn, _, _, _, _ = _core()
    w = max(64, min(2048, width))
    h = max(64, min(2048, height))
    try:
        model_name = (model or "").strip() or None
        result = create_image_fn(
            prompt,
            w,
            h,
            provider_name=provider.lower(),  # type: ignore[arg-type]
            model=model_name,
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
    resize_scale: float = Form(1.0),
    resize_width: int = Form(0),
    resize_height: int = Form(0),
    resize_keep_aspect: bool = Form(True),
) -> Response:
    _, _, _, _, _, adjust_image_fn, _, _, _ = _core()
    try:
        body = normalize_upload_to_png(await image.read())
        scale = max(0.01, min(10.0, resize_scale))
        rw = max(0, min(8192, resize_width))
        rh = max(0, min(8192, resize_height))
        result = adjust_image_fn(
            body,
            brightness=brightness,
            contrast=contrast,
            saturation=saturation,
            sharpness=sharpness,
            blur_radius=blur_radius,
            rotate_degrees=rotate_degrees,
            flip=flip,
            resize_scale=scale,
            resize_width=rw,
            resize_height=rh,
            resize_keep_aspect=resize_keep_aspect,
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
    _, _, _, _, _, _, tile_image_fn, _, _ = _core()
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
    _, _, _, _, _, _, _, generate_texture_map_fn, _ = _core()
    try:
        body = normalize_upload_to_png(await image.read())
        result = generate_texture_map_fn(body, map_type, strength=strength)
    except Exception as e:
        status, detail = _handle_provider_error(e)
        raise HTTPException(status_code=status, detail=detail)
    return Response(content=result, media_type="image/png")


@app.get("/asset-types")
async def asset_types_list() -> list:
    from game_images.asset_types import get_asset_type_registry

    return get_asset_type_registry().list_public()


@app.get("/projects")
async def projects_list() -> list:
    return _get_projects().list_projects()


class ProjectCreateBody(BaseModel):
    name: str
    notes: str | None = None


class ProjectUpdateBody(BaseModel):
    name: str | None = None
    notes: str | None = None


class ProjectAssetBody(BaseModel):
    asset_id: str
    role: str | None = None
    sort_order: int | None = None


@app.post("/projects")
async def projects_create(body: ProjectCreateBody) -> dict:
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name is required.")
    return _get_projects().create_project(name, notes=body.notes)


@app.get("/projects/{project_id}")
async def projects_get(project_id: str) -> dict:
    project = _get_projects().get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.patch("/projects/{project_id}")
async def projects_update(project_id: str, body: ProjectUpdateBody) -> dict:
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update.")
    if "name" in payload and not (payload["name"] or "").strip():
        raise HTTPException(status_code=400, detail="Project name cannot be empty.")
    project = _get_projects().update_project(project_id, **payload)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.delete("/projects/{project_id}")
async def projects_delete(project_id: str) -> dict:
    if not _get_projects().delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"deleted": project_id}


@app.post("/projects/{project_id}/assets")
async def projects_add_asset(project_id: str, body: ProjectAssetBody) -> dict:
    store = _get_projects()
    if not store.add_asset(
        project_id,
        body.asset_id,
        role=body.role,
        sort_order=body.sort_order,
    ):
        raise HTTPException(status_code=404, detail="Project or asset not found")
    project = store.get_project(project_id)
    return project or {}


@app.delete("/projects/{project_id}/assets/{asset_id}")
async def projects_remove_asset(project_id: str, asset_id: str) -> dict:
    if not _get_projects().remove_asset(project_id, asset_id):
        raise HTTPException(status_code=404, detail="Project or asset membership not found")
    return {"removed": asset_id, "project_id": project_id}


@app.get("/library")
async def library_list(
    type: str | None = Query(None, description="Filter by type: image, mask, result (comma-separated for multiple)"),
    tag: str | None = Query(None),
    asset_type: str | None = Query(None, description="Filter by asset_type_id (comma-separated)"),
    project: str | None = Query(None, description="Filter by project id"),
) -> list:
    """List images in the library."""
    lib = _get_library()
    return lib.list_images(type=type, tag=tag, asset_type=asset_type, project_id=project)


@app.post("/library/import")
async def library_import(
    image: UploadFile = File(...),
    type: str = Form("image"),
    asset_type_id: str = Form("generic_image"),
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
    img_id = lib.add_image(
        png_bytes,
        filename,
        type,
        asset_type_id=asset_type_id.strip() or "generic_image",
    )
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


class LibraryUpdateBody(BaseModel):
    """Update library metadata. Only provided fields are changed."""

    filename: str | None = None
    prompt: str | None = None
    tags: str | None = None
    notes: str | None = None
    asset_type_id: str | None = None


@app.patch("/library/{img_id}")
async def library_update(img_id: str, body: LibraryUpdateBody) -> dict:
    """Update metadata (e.g. rename via filename)."""
    lib = _get_library()
    if not lib.get_metadata(img_id):
        raise HTTPException(status_code=404, detail="Image not found")
    payload = body.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No fields to update.")
    if "filename" in payload and not (payload["filename"] or "").strip():
        raise HTTPException(status_code=400, detail="Filename cannot be empty.")
    lib.update_metadata(img_id, **payload)
    meta = lib.get_metadata(img_id)
    return meta or {}


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
    inherited_type = lib.asset_type_for_source(source_id)
    img_id = lib.add_image(
        png_bytes,
        "result.png",
        "result",
        prompt=prompt or None,
        source_id=source_id or None,
        mask_id=mask_id or None,
        asset_type_id=inherited_type,
    )
    meta = lib.get_metadata(img_id)
    return {"id": img_id, "metadata": meta}


class KeysUpdateBody(BaseModel):
    """Update stored API keys. Omit a field to leave it unchanged; use empty string to remove."""

    openai_api_key: str | None = None
    openai_oauth_token: str | None = None
    openai_auth_mode: str | None = None
    fal_api_key: str | None = None
    gemini_api_key: str | None = None
    minimax_api_key: str | None = None


@app.get("/settings/keys")
async def settings_keys_get() -> dict:
    from game_images.settings import keys_status

    return keys_status()


@app.put("/settings/keys")
async def settings_keys_put(body: KeysUpdateBody) -> dict:
    from game_images.settings import update_keys

    return update_keys(
        openai_api_key=body.openai_api_key,
        openai_oauth_token=body.openai_oauth_token,
        openai_auth_mode=body.openai_auth_mode,
        fal_api_key=body.fal_api_key,
        gemini_api_key=body.gemini_api_key,
        minimax_api_key=body.minimax_api_key,
    )


@app.get("/settings/models")
async def settings_models_get() -> dict:
    from game_images.model_catalog import get_catalog

    return get_catalog()


@app.post("/settings/models/discover")
async def settings_models_discover() -> dict:
    from game_images.model_catalog import discover_all

    return discover_all()


class OpenAiOAuthStartBody(BaseModel):
    redirect_port: int = 8000


@app.post("/settings/oauth/openai/start")
async def openai_oauth_start(body: OpenAiOAuthStartBody) -> dict:
    """Return ChatGPT OAuth URL; opens browser to sign in."""
    from game_images.openai_codex_oauth import start_login

    port = max(1, min(65535, body.redirect_port))
    return start_login(redirect_port=port)


@app.get("/settings/oauth/openai/poll")
async def openai_oauth_poll(state: str = Query(...)) -> dict:
    from game_images.openai_codex_oauth import poll_login

    return poll_login(state)


@app.get("/auth/openai/callback", response_class=HTMLResponse)
async def openai_oauth_callback(
    state: str | None = Query(None),
    code: str | None = Query(None),
    error: str | None = Query(None),
) -> str:
    from game_images.openai_codex_oauth import (
        ERROR_HTML,
        SUCCESS_HTML,
        complete_login,
        fail_login,
    )
    from game_images.settings import save_openai_oauth_session

    if error:
        if state:
            fail_login(state, error)
        return ERROR_HTML.replace("{message}", error.replace("<", "&lt;"))
    if not state or not code:
        return ERROR_HTML.replace("{message}", "Missing authorization code.")
    try:
        tokens = complete_login(state, code)
        save_openai_oauth_session(tokens)
        return SUCCESS_HTML
    except Exception as e:
        fail_login(state, str(e))
        return ERROR_HTML.replace("{message}", str(e).replace("<", "&lt;"))


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "app": "game-images"}
