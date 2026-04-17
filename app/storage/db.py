"""SQLite 连接与 schema. 使用单进程内互斥锁防并发写入锁表."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_LOCK = threading.Lock()

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS session (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    meta        TEXT
);

CREATE TABLE IF NOT EXISTS "case" (
    id               TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL,
    chief_complaint  TEXT NOT NULL,
    symptoms         TEXT NOT NULL,
    medical_history  TEXT DEFAULT '',
    exam_results     TEXT DEFAULT '',
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES session(id)
);

CREATE TABLE IF NOT EXISTS message (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL,
    round               INTEGER NOT NULL DEFAULT 1,
    role                TEXT NOT NULL,         -- routing / opinion / report / safety
    payload_json        TEXT NOT NULL,
    inference_meta_json TEXT DEFAULT '{}',
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (session_id) REFERENCES session(id)
);

CREATE INDEX IF NOT EXISTS idx_case_session ON "case"(session_id);
CREATE INDEX IF NOT EXISTS idx_message_session_round ON message(session_id, round);
"""


def get_conn(db_path: str) -> sqlite3.Connection:
    """返回一个允许跨线程复用的连接. 调用方必要时配合 `write_lock` 使用."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(db_path: str) -> None:
    conn = get_conn(db_path)
    with _LOCK:
        conn.executescript(SCHEMA_SQL)


def write_lock() -> threading.Lock:
    """进程内全局写锁, 供 repo 的写操作包一层避免 SQLite 锁表."""
    return _LOCK
