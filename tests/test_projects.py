"""Tests for projects and library asset_type_id."""

import io
from pathlib import Path

import pytest
from PIL import Image

from game_images.library import Library
from game_images.projects import ProjectStore


def _tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=(10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def lib_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def library(lib_root: Path) -> Library:
    return Library(root=lib_root)


@pytest.fixture
def projects(lib_root: Path) -> ProjectStore:
    return ProjectStore(root=lib_root)


def test_create_project_and_add_asset(library: Library, projects: ProjectStore) -> None:
    img_id = library.add_image(_tiny_png(), "a.png", "image", asset_type_id="texture")
    project = projects.create_project("Level 1")
    assert projects.add_asset(project["id"], img_id)
    detail = projects.get_project(project["id"])
    assert detail is not None
    assert detail["asset_count"] == 1
    assert len(detail["assets"]) == 1
    assert detail["assets"][0]["asset_type_id"] == "texture"


def test_asset_in_multiple_projects(library: Library, projects: ProjectStore) -> None:
    img_id = library.add_image(_tiny_png(), "shared.png", "image")
    p1 = projects.create_project("A")
    p2 = projects.create_project("B")
    projects.add_asset(p1["id"], img_id)
    projects.add_asset(p2["id"], img_id)
    listed = library.list_images()
    item = next(i for i in listed if i["id"] == img_id)
    assert len(item["projects"]) == 2


def test_delete_project_keeps_asset(library: Library, projects: ProjectStore) -> None:
    img_id = library.add_image(_tiny_png(), "keep.png", "image")
    project = projects.create_project("Temp")
    projects.add_asset(project["id"], img_id)
    assert projects.delete_project(project["id"])
    assert library.get_metadata(img_id) is not None
    item = library.get_metadata(img_id)
    assert item is not None
    assert item["projects"] == []


def test_filter_by_asset_type(library: Library) -> None:
    library.add_image(_tiny_png(), "t.png", "image", asset_type_id="texture")
    library.add_image(_tiny_png(), "s.png", "image", asset_type_id="skydome")
    textures = library.list_images(asset_type="texture")
    assert len(textures) == 1
    assert textures[0]["asset_type_id"] == "texture"


def test_filter_by_project(library: Library, projects: ProjectStore) -> None:
    a = library.add_image(_tiny_png(), "a.png", "image")
    library.add_image(_tiny_png(), "b.png", "image")
    project = projects.create_project("Filter test")
    projects.add_asset(project["id"], a)
    filtered = library.list_images(project_id=project["id"])
    assert len(filtered) == 1
    assert filtered[0]["id"] == a


def test_result_inherits_asset_type(library: Library) -> None:
    src = library.add_image(_tiny_png(), "src.png", "image", asset_type_id="texture")
    inherited = library.asset_type_for_source(src)
    assert inherited == "texture"
    result_id = library.add_image(
        _tiny_png(), "out.png", "result", source_id=src, asset_type_id=inherited
    )
    meta = library.get_metadata(result_id)
    assert meta is not None
    assert meta["asset_type_id"] == "texture"


def test_update_asset_role(library: Library, projects: ProjectStore) -> None:
    img_id = library.add_image(_tiny_png(), "a.png", "image", asset_type_id="texture")
    project = projects.create_project("Roles")
    projects.add_asset(project["id"], img_id, role="albedo")
    assert projects.update_asset(project["id"], img_id, role="normal")
    detail = projects.get_project(project["id"])
    assert detail is not None
    assert detail["assets"][0]["role"] == "normal"


def test_project_asset_lists_source_id(library: Library, projects: ProjectStore) -> None:
    src = library.add_image(_tiny_png(), "albedo.png", "image", asset_type_id="texture")
    derived = library.add_image(
        _tiny_png(), "albedo_normal.png", "image", source_id=src, asset_type_id="texture"
    )
    project = projects.create_project("Derivatives")
    projects.add_asset(project["id"], src, role="albedo")
    projects.add_asset(project["id"], derived, role="normal")
    assets = projects.list_project_assets(project["id"])
    by_id = {a["asset_id"]: a for a in assets}
    assert by_id[derived]["source_id"] == src
