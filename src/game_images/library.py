"""Image library: local file storage with SQLite index."""

import io
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from PIL import Image

ImageType = Literal["image", "mask", "result"]

_INVALID_FILENAME_CHARS = '<>:"/\\|?*\0'
DEFAULT_ASSET_TYPE_ID = "generic_image"


def sanitize_filename(name: str) -> str:
    """Normalize a display filename (library files stay {id}.png on disk)."""
    cleaned = (name or "").strip()
    cleaned = Path(cleaned).name
    cleaned = "".join(
        c for c in cleaned if c.isprintable() and c not in _INVALID_FILENAME_CHARS
    ).strip()
    if not cleaned or cleaned in (".", ".."):
        return "untitled.png"
    if len(cleaned) > 200:
        p = Path(cleaned)
        suffix = p.suffix if p.suffix else ".png"
        stem = p.stem[: max(1, 200 - len(suffix))]
        cleaned = stem + suffix
    return cleaned


def get_library_path() -> Path:
    """Resolve library root from GAME_IMAGES_LIBRARY env or default."""
    env_path = os.environ.get("GAME_IMAGES_LIBRARY")
    if env_path:
        p = Path(env_path).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    # Default: user data dir
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", "")) or Path.home() / "AppData" / "Local"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", "")) or Path.home() / ".local" / "share"
    try:
        p = (base / "game-images").resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    except OSError:
        pass
    # Fallback: ./library/ in project root
    project_root = Path(__file__).resolve().parent.parent.parent
    p = (project_root / "library").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


class Library:
    """Image library with SQLite index and PNG files on disk."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_library_path()
        self.images_dir = self.root / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self.root / "library.db"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    type TEXT NOT NULL CHECK (type IN ('image', 'mask', 'result')),
                    width INTEGER,
                    height INTEGER,
                    created_at TEXT NOT NULL,
                    prompt TEXT,
                    source_id TEXT,
                    mask_id TEXT,
                    tags TEXT,
                    notes TEXT,
                    extra TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    extra TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_assets (
                    project_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    role TEXT,
                    sort_order INTEGER,
                    PRIMARY KEY (project_id, asset_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_project_assets_asset
                ON project_assets(asset_id)
            """)
            self._migrate_schema(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(images)").fetchall()
        }
        if "asset_type_id" not in cols:
            conn.execute(
                "ALTER TABLE images ADD COLUMN asset_type_id TEXT NOT NULL DEFAULT 'generic_image'"
            )

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        if d.get("extra"):
            try:
                d["extra"] = json.loads(d["extra"])
            except (json.JSONDecodeError, TypeError):
                d["extra"] = None
        d.setdefault("asset_type_id", DEFAULT_ASSET_TYPE_ID)
        return d

    def _attach_projects(self, conn: sqlite3.Connection, items: list[dict]) -> None:
        if not items:
            return
        ids = [item["id"] for item in items]
        placeholders = ",".join("?" * len(ids))
        rows = conn.execute(
            f"""
            SELECT pa.asset_id, p.id, p.name
            FROM project_assets pa
            JOIN projects p ON p.id = pa.project_id
            WHERE pa.asset_id IN ({placeholders})
            ORDER BY p.name ASC
            """,
            ids,
        ).fetchall()
        by_asset: dict[str, list[dict]] = {i: [] for i in ids}
        for row in rows:
            by_asset.setdefault(row[0], []).append({"id": row[1], "name": row[2]})
        for item in items:
            item["projects"] = by_asset.get(item["id"], [])

    def add_image(
        self,
        data: bytes,
        filename: str,
        type: ImageType,
        *,
        width: int | None = None,
        height: int | None = None,
        prompt: str | None = None,
        source_id: str | None = None,
        mask_id: str | None = None,
        tags: str | None = None,
        notes: str | None = None,
        extra: dict | None = None,
        asset_type_id: str | None = None,
    ) -> str:
        """Add image to library. Returns id."""
        img_id = str(uuid.uuid4())
        file_path = self.images_dir / f"{img_id}.png"
        filename = sanitize_filename(filename or f"{img_id}.png")
        resolved_type = asset_type_id or DEFAULT_ASSET_TYPE_ID
        if type == "mask":
            resolved_type = DEFAULT_ASSET_TYPE_ID

        # Normalize to PNG
        png_bytes = self._normalize_to_png(data)
        file_path.write_bytes(png_bytes)

        # Get dimensions if not provided
        if width is None or height is None:
            with Image.open(io.BytesIO(png_bytes)) as img:
                w, h = img.size
            width = width or w
            height = height or h

        created_at = datetime.now(timezone.utc).isoformat()
        extra_json = json.dumps(extra) if extra else None

        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO images (id, filename, type, width, height, created_at,
                    prompt, source_id, mask_id, tags, notes, extra, asset_type_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    img_id,
                    filename,
                    type,
                    width,
                    height,
                    created_at,
                    prompt,
                    source_id,
                    mask_id,
                    tags,
                    notes,
                    extra_json,
                    resolved_type,
                ),
            )
        return img_id

    def _normalize_to_png(self, data: bytes) -> bytes:
        buf = io.BytesIO(data)
        img = Image.open(buf)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    def list_images(
        self,
        type: ImageType | str | None = None,
        tag: str | None = None,
        asset_type: str | None = None,
        project_id: str | None = None,
    ) -> list[dict]:
        """List images with optional filters."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            conditions = []
            params: list = []
            join = ""
            if type:
                types = [t.strip() for t in str(type).split(",") if t.strip()]
                if types:
                    placeholders = ",".join("?" * len(types))
                    conditions.append(f"i.type IN ({placeholders})")
                    params.extend(types)
            if tag:
                conditions.append(
                    "(i.tags LIKE ? OR i.tags LIKE ? OR i.tags LIKE ? OR i.tags = ?)"
                )
                params.extend([f"%{tag}%", f"{tag},%", f"%,{tag}", tag])
            if asset_type:
                types_at = [t.strip() for t in asset_type.split(",") if t.strip()]
                if types_at:
                    placeholders = ",".join("?" * len(types_at))
                    conditions.append(f"i.asset_type_id IN ({placeholders})")
                    params.extend(types_at)
            if project_id:
                join = "JOIN project_assets pa ON pa.asset_id = i.id"
                conditions.append("pa.project_id = ?")
                params.append(project_id)
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            cursor = conn.execute(
                f"SELECT i.* FROM images i {join} {where} ORDER BY i.created_at DESC",
                params,
            )
            items = [self._row_to_dict(row) for row in cursor.fetchall()]
            self._attach_projects(conn, items)
            return items

    def get_image(self, img_id: str) -> bytes | None:
        """Get image bytes by id."""
        path = self.images_dir / f"{img_id}.png"
        if not path.exists():
            return None
        return path.read_bytes()

    def get_metadata(self, img_id: str) -> dict | None:
        """Get metadata by id."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM images WHERE id = ?", (img_id,)
            ).fetchone()
            if row is None:
                return None
            item = self._row_to_dict(row)
            self._attach_projects(conn, [item])
            return item

    def rename(self, img_id: str, filename: str) -> bool:
        """Rename the display filename for a library item."""
        return self.update_metadata(img_id, filename=sanitize_filename(filename))

    def update_metadata(self, img_id: str, **kwargs: str | int | dict | None) -> bool:
        """Update metadata fields. Returns True if found."""
        allowed = {"filename", "prompt", "tags", "notes", "extra", "asset_type_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        if "filename" in updates:
            updates["filename"] = sanitize_filename(str(updates["filename"]))
        if "extra" in updates and isinstance(updates["extra"], dict):
            updates["extra"] = json.dumps(updates["extra"])
        if not updates:
            return True
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [img_id]
        with sqlite3.connect(self._db_path) as conn:
            cur = conn.execute(
                f"UPDATE images SET {set_clause} WHERE id = ?",
                values,
            )
            return cur.rowcount > 0

    def delete(self, img_id: str) -> bool:
        """Remove image from library. Returns True if found."""
        path = self.images_dir / f"{img_id}.png"
        if path.exists():
            path.unlink()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM project_assets WHERE asset_id = ?", (img_id,))
            cur = conn.execute("DELETE FROM images WHERE id = ?", (img_id,))
            return cur.rowcount > 0

    def asset_type_for_source(self, source_id: str | None) -> str:
        if not source_id:
            return DEFAULT_ASSET_TYPE_ID
        meta = self.get_metadata(source_id)
        if not meta:
            return DEFAULT_ASSET_TYPE_ID
        return meta.get("asset_type_id") or DEFAULT_ASSET_TYPE_ID

    def duplicate_image(
        self,
        img_id: str,
        *,
        filename: str | None = None,
        source_id: str | None = None,
        extra: dict | None = None,
    ) -> str | None:
        """Copy image bytes to a new library entry. Returns new id or None."""
        meta = self.get_metadata(img_id)
        if meta is None:
            return None
        data = self.get_image(img_id)
        if not data:
            return None
        stem = Path(meta["filename"]).stem if meta.get("filename") else img_id[:8]
        new_filename = sanitize_filename(filename or f"{stem}_fork.png")
        merged_extra = dict(meta.get("extra") or {})
        if extra:
            merged_extra.update(extra)
        fork_source = source_id if source_id is not None else img_id
        return self.add_image(
            data,
            new_filename,
            meta["type"],
            width=meta.get("width"),
            height=meta.get("height"),
            prompt=meta.get("prompt"),
            source_id=fork_source,
            mask_id=meta.get("mask_id"),
            tags=meta.get("tags"),
            notes=meta.get("notes"),
            extra=merged_extra or None,
            asset_type_id=meta.get("asset_type_id"),
        )
