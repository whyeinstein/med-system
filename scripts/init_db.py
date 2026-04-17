"""初始化 SQLite schema.

使用:
    python scripts/init_db.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

# 允许脚本直接运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.storage.db import init_schema  # noqa: E402


def main() -> None:
    cfg_path = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    db_path = cfg["storage"]["sqlite_path"]
    init_schema(db_path)
    print(f"[init_db] schema initialized at: {db_path}")


if __name__ == "__main__":
    main()
