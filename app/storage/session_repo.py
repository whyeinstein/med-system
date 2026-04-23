"""session 表 CRUD."""
from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Dict, List, Optional

from app.storage.db import write_lock


class SessionRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, meta: Optional[Dict] = None) -> str:
        sid = uuid.uuid4().hex
        with write_lock():
            self._conn.execute(
                "INSERT INTO session (id, meta) VALUES (?, ?)",
                (sid, json.dumps(meta or {}, ensure_ascii=False)),
            )
        return sid

    def get(self, sid: str) -> Optional[Dict]:
        row = self._conn.execute(
            "SELECT id, created_at, meta FROM session WHERE id = ?", (sid,)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "meta": json.loads(row["meta"] or "{}"),
        }

    def list(self, limit: int = 50) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT id, created_at, meta FROM session ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {"id": r["id"], "created_at": r["created_at"], "meta": json.loads(r["meta"] or "{}")}
            for r in rows
        ]

    def delete(self, sid: str) -> None:
        with write_lock():
            self._conn.execute("DELETE FROM message WHERE session_id = ?", (sid,))
            self._conn.execute('DELETE FROM "case" WHERE session_id = ?', (sid,))
            self._conn.execute("DELETE FROM session WHERE id = ?", (sid,))
