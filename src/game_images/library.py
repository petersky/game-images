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

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        if d.get("extra"):
            try:
                d["extra"] = json.loads(d["extra"])
            except (json.JSONDecodeError, TypeError):
                d["extra"] = None
        return d

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
    ) -> str:
        """Add image to library. Returns id."""
        img_id = str(uuid.uuid4())
        file_path = self.images_dir / f"{img_id}.png"
        filename = sanitize_filename(filename or f"{img_id}.png")

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
                    prompt, source_id, mask_id, tags, notes, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    img_id,
                    filename,
                    type,
                    width,
                    height,
                    created_at,
                    prompt, source_id, mask_id, tags, notes, extra_json,
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
    ) -> list[dict]:
        """List images with optional filters. type can be 'image','mask','result' or comma-separated."""
        with sqlite3.connect(self._db_path) as conn:
            conn.row_factory = sqlite3.Row
            conditions = []
            params: list = []
            if type:
                types = [t.strip() for t in str(type).split(",") if t.strip()]
                if types:
                    placeholders = ",".join("?" * len(types))
                    conditions.append(f"type IN ({placeholders})")
                    params.extend(types)
            if tag:
                conditions.append(
                    "(tags LIKE ? OR tags LIKE ? OR tags LIKE ? OR tags = ?)"
                )
                params.extend([f"%{tag}%", f"{tag},%", f"%,{tag}", tag])
            where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
            cursor = conn.execute(
                f"SELECT * FROM images {where} ORDER BY created_at DESC",
                params,
            )
            return [self._row_to_dict(row) for row in cursor.fetchall()]

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
            return self._row_to_dict(row)

    def rename(self, img_id: str, filename: str) -> bool:
        """Rename the display filename for a library item."""
        return self.update_metadata(img_id, filename=sanitize_filename(filename))

    def update_metadata(self, img_id: str, **kwargs: str | int | dict | None) -> bool:
        """Update metadata fields. Returns True if found."""
        allowed = {"filename", "prompt", "tags", "notes", "extra"}
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
            cur = conn.execute("DELETE FROM images WHERE id = ?", (img_id,))
            return cur.rowcount > 0
