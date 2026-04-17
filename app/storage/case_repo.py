"""case 表 CRUD."""
from __future__ import annotations

import sqlite3
import uuid
from typing import Optional

from app.schemas.case import CaseSummary
from app.storage.db import write_lock


class CaseRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(self, session_id: str, case: CaseSummary) -> str:
        cid = case.case_id or uuid.uuid4().hex
        with write_lock():
            self._conn.execute(
                """
                INSERT INTO "case"
                    (id, session_id, chief_complaint, symptoms, medical_history, exam_results)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cid,
                    session_id,
                    case.chief_complaint,
                    case.symptoms,
                    case.medical_history,
                    case.exam_results,
                ),
            )
        return cid

    def get(self, case_id: str) -> Optional[CaseSummary]:
        row = self._conn.execute(
            'SELECT * FROM "case" WHERE id = ?', (case_id,)
        ).fetchone()
        if not row:
            return None
        return CaseSummary(
            case_id=row["id"],
            chief_complaint=row["chief_complaint"],
            symptoms=row["symptoms"],
            medical_history=row["medical_history"] or "",
            exam_results=row["exam_results"] or "",
        )
