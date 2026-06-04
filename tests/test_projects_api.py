"""API tests for Phase 3 project fork and export."""

import io
import sys
import zipfile
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
    Image.new("RGB", (8, 8), color=(50, 60, 70)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import web.app as webapp

    lib = Library(root=tmp_path)
    store = ProjectStore(root=tmp_path)
    monkeypatch.setattr(webapp, "_get_library", lambda: lib)
    monkeypatch.setattr(webapp, "_get_projects", lambda: store)
    monkeypatch.setattr(webapp, "_library", lib)
    monkeypatch.setattr(webapp, "_projects", store)
    return TestClient(webapp.app)


def test_projects_fork_endpoint(api_client: TestClient) -> None:
    import web.app as webapp

    lib = webapp._get_library()
    img_id = lib.add_image(_tiny_png(), "tile.png", "image", asset_type_id="texture")
    project = webapp._get_projects().create_project("Level")
    webapp._get_projects().add_asset(project["id"], img_id)

    res = api_client.post(
        f"/projects/{project['id']}/fork",
        json={"asset_id": img_id, "role": "albedo"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["forked_from"] == img_id
    assert data["id"] != img_id


def test_projects_export_endpoint(api_client: TestClient) -> None:
    import web.app as webapp

    lib = webapp._get_library()
    img_id = lib.add_image(_tiny_png(), "grass.png", "image")
    project = webapp._get_projects().create_project("Export")
    webapp._get_projects().add_asset(project["id"], img_id, role="albedo")

    res = api_client.get(f"/projects/{project['id']}/export?preset=png_by_role")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
        assert "albedo.png" in zf.namelist()


def test_export_presets_list(api_client: TestClient) -> None:
    res = api_client.get("/projects/export-presets")
    assert res.status_code == 200
    ids = {p["id"] for p in res.json()}
    assert "texture_set" in ids
