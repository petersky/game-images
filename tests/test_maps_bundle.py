"""Tests for texture maps bundle API."""

import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from game_images.library import Library
from game_images.projects import ProjectStore

_MAIN_ROOT = Path(__file__).resolve().parents[1]
if str(_MAIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_MAIN_ROOT))


def _tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color=(100, 120, 140)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def lib_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def api_client(lib_root: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import web.app as webapp

    lib = Library(root=lib_root)
    store = ProjectStore(root=lib_root)
    monkeypatch.setattr(webapp, "_get_library", lambda: lib)
    monkeypatch.setattr(webapp, "_get_projects", lambda: store)
    monkeypatch.setattr(webapp, "_library", lib)
    monkeypatch.setattr(webapp, "_projects", store)
    return TestClient(webapp.app)


def test_maps_bundle_saves_linked_maps(api_client: TestClient, lib_root: Path) -> None:
    import web.app as webapp

    lib = webapp._get_library()
    png = _tiny_png()
    src_id = lib.add_image(png, "stone_albedo.png", "image", asset_type_id="texture")
    project = webapp._get_projects().create_project("Textures")

    res = api_client.post(
        "/maps/bundle",
        files={"image": ("stone_albedo.png", png, "image/png")},
        data={"source_id": src_id, "project_id": project["id"], "strength": "1.0"},
    )
    assert res.status_code == 200
    data = res.json()
    assert len(data["maps"]) == 2
    roles = {m["role"] for m in data["maps"]}
    assert roles == {"normal", "roughness"}
    for entry in data["maps"]:
        meta = entry["metadata"]
        assert meta["source_id"] == src_id
        assert meta["asset_type_id"] == "texture"

    detail = webapp._get_projects().get_project(project["id"])
    assert detail is not None
    assert detail["asset_count"] == 2
    project_roles = {a["role"] for a in detail["assets"]}
    assert project_roles == {"normal", "roughness"}


def test_skydome_lightmap_stub_returns_501(api_client: TestClient) -> None:
    res = api_client.post("/skydome/lightmap")
    assert res.status_code == 501
