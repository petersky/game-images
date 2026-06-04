"""Project collections and project–asset membership."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from game_images.library import Library, get_library_path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectStore:
    """Projects and many-to-many asset membership (same DB as library)."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_library_path()
        self._db_path = self.root / "library.db"
        self._library = Library(root=self.root)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def list_projects(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT p.*,
                    (SELECT COUNT(*) FROM project_assets pa WHERE pa.project_id = p.id) AS asset_count
                FROM projects p
                ORDER BY p.updated_at DESC, p.created_at DESC
                """
            ).fetchall()
        return [self._project_row(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT p.*,
                    (SELECT COUNT(*) FROM project_assets pa WHERE pa.project_id = p.id) AS asset_count
                FROM projects p WHERE p.id = ?
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        project = self._project_row(row)
        project["assets"] = self.list_project_assets(project_id)
        return project

    def create_project(
        self,
        name: str,
        *,
        notes: str | None = None,
        extra: dict | None = None,
    ) -> dict[str, Any]:
        project_id = str(uuid.uuid4())
        now = _utc_now()
        extra_json = json.dumps(extra) if extra else None
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, slug, notes, created_at, updated_at, extra)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, name.strip(), None, notes, now, now, extra_json),
            )
        meta = self.get_project(project_id)
        assert meta is not None
        return meta

    def update_project(
        self,
        project_id: str,
        *,
        name: str | None = None,
        notes: str | None = None,
        extra: dict | None = None,
    ) -> dict[str, Any] | None:
        updates: dict[str, Any] = {"updated_at": _utc_now()}
        if name is not None:
            updates["name"] = name.strip()
        if notes is not None:
            updates["notes"] = notes
        if extra is not None:
            updates["extra"] = json.dumps(extra)
        if len(updates) <= 1:
            return self.get_project(project_id)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [project_id]
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE projects SET {set_clause} WHERE id = ?",
                values,
            )
            if cur.rowcount == 0:
                return None
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM project_assets WHERE project_id = ?",
                (project_id,),
            )
            cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            return cur.rowcount > 0

    def add_asset(
        self,
        project_id: str,
        asset_id: str,
        *,
        role: str | None = None,
        sort_order: int | None = None,
    ) -> bool:
        if self._library.get_metadata(asset_id) is None:
            return False
        if self.get_project(project_id) is None:
            return False
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO project_assets (project_id, asset_id, added_at, role, sort_order)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_id, asset_id) DO UPDATE SET
                    role = excluded.role,
                    sort_order = excluded.sort_order
                """,
                (project_id, asset_id, now, role, sort_order),
            )
            conn.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (now, project_id),
            )
        return True

    def remove_asset(self, project_id: str, asset_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM project_assets WHERE project_id = ? AND asset_id = ?",
                (project_id, asset_id),
            )
            if cur.rowcount:
                conn.execute(
                    "UPDATE projects SET updated_at = ? WHERE id = ?",
                    (_utc_now(), project_id),
                )
            return cur.rowcount > 0

    def update_asset(
        self,
        project_id: str,
        asset_id: str,
        *,
        role: str | None = None,
        sort_order: int | None = None,
    ) -> bool:
        updates: dict[str, Any] = {}
        if role is not None:
            updates["role"] = role.strip() or None
        if sort_order is not None:
            updates["sort_order"] = sort_order
        if not updates:
            return self.get_project(project_id) is not None and any(
                a["asset_id"] == asset_id
                for a in self.list_project_assets(project_id)
            )
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [project_id, asset_id]
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE project_assets SET {set_clause} WHERE project_id = ? AND asset_id = ?",
                values,
            )
            if cur.rowcount:
                conn.execute(
                    "UPDATE projects SET updated_at = ? WHERE id = ?",
                    (_utc_now(), project_id),
                )
            return cur.rowcount > 0

    def list_project_assets(self, project_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT pa.*, i.filename, i.type, i.width, i.height, i.asset_type_id,
                    i.source_id, i.created_at AS asset_created_at
                FROM project_assets pa
                JOIN images i ON i.id = pa.asset_id
                WHERE pa.project_id = ?
                ORDER BY pa.sort_order ASC, pa.added_at DESC
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_projects_for_asset(self, asset_id: str) -> list[dict[str, str]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT p.id, p.name
                FROM project_assets pa
                JOIN projects p ON p.id = pa.project_id
                WHERE pa.asset_id = ?
                ORDER BY p.name ASC
                """,
                (asset_id,),
            ).fetchall()
        return [{"id": row["id"], "name": row["name"]} for row in rows]

    @staticmethod
    def _project_row(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        if d.get("extra"):
            try:
                d["extra"] = json.loads(d["extra"])
            except (json.JSONDecodeError, TypeError):
                d["extra"] = None
        return d
