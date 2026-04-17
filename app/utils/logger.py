"""结构化 JSON 行日志. 本阶段仅 stdout, 阶段 5 再补文件 handler."""
from __future__ import annotations

import json
import logging
import sys
from typing import Any


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extras = getattr(record, "extras", None)
        if isinstance(extras, dict):
            payload.update(extras)
        return json.dumps(payload, ensure_ascii=False)


_CONFIGURED = False


def get_logger(name: str = "med-system", level: str = "INFO") -> logging.Logger:
    """懒加载式全局 logger 工厂."""
    global _CONFIGURED
    root = logging.getLogger()
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(level)
        _CONFIGURED = True
    return logging.getLogger(name)


def log_with(logger: logging.Logger, level: str, msg: str, **extras: Any) -> None:
    """附带结构化字段打日志."""
    logger.log(getattr(logging, level.upper()), msg, extra={"extras": extras})
