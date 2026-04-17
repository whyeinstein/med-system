"""message 表 CRUD. payload_json 保存 Pydantic 模型序列化后的 JSON."""
from __future__ import annotations

import json
import sqlite3
from typing import Dict, List, Optional

from app.storage.db import write_lock


class MessageRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(
        self,
        session_id: str,
        role: str,
        payload: Dict,
        inference_meta: Optional[Dict] = None,
        round_: int = 1,
    ) -> int:
        with write_lock():
            cur = self._conn.execute(
                """
                INSERT INTO message
                    (session_id, round, role, payload_json, inference_meta_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    round_,
                    role,
                    json.dumps(payload, ensure_ascii=False, default=str),
                    json.dumps(inference_meta or {}, ensure_ascii=False, default=str),
                ),
            )
        return int(cur.lastrowid or 0)

    def list(self, session_id: str) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM message WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def list_by_round(self, session_id: str, round_: int) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM message WHERE session_id = ? AND round = ? ORDER BY id ASC",
            (session_id, round_),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "round": row["round"],
            "role": row["role"],
            "payload": json.loads(row["payload_json"]),
            "inference_meta": json.loads(row["inference_meta_json"] or "{}"),
            "created_at": row["created_at"],
        }
