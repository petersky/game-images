"""Tests for project export zip packs."""

import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from game_images.library import Library
from game_images.project_export import build_project_export_zip, list_export_presets
from game_images.projects import ProjectStore


def _tiny_png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color=(1, 2, 3)).save(buf, format="PNG")
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


def test_list_export_presets() -> None:
    presets = list_export_presets()
    ids = {p["id"] for p in presets}
    assert "png_by_role" in ids
    assert "texture_set" in ids


def test_build_export_zip_by_role(library: Library, projects: ProjectStore) -> None:
    a = library.add_image(_tiny_png(), "rock.png", "image", asset_type_id="texture")
    project = projects.create_project("Export me")
    projects.add_asset(project["id"], a, role="albedo")
    detail = projects.get_project(project["id"])
    assert detail is not None
    data, filename = build_project_export_zip(library, detail, "png_by_role")
    assert filename.endswith("_png_by_role.zip")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
    assert "albedo.png" in names


def test_texture_set_filters_roles(library: Library, projects: ProjectStore) -> None:
    albedo = library.add_image(_tiny_png(), "a.png", "image")
    skydome = library.add_image(_tiny_png(), "sky.png", "image", asset_type_id="skydome")
    project = projects.create_project("Mixed")
    projects.add_asset(project["id"], albedo, role="albedo")
    projects.add_asset(project["id"], skydome, role="skydome_main")
    detail = projects.get_project(project["id"])
    assert detail is not None
    data, _ = build_project_export_zip(library, detail, "texture_set")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
    assert "albedo.png" in names
    assert not any("sky" in n for n in names)
