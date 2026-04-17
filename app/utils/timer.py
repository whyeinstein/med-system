"""推理耗时计时器. 同时提供装饰器与上下文管理器两种用法."""
from __future__ import annotations

import time
from contextlib import ContextDecorator
from functools import wraps
from typing import Callable


class Timer(ContextDecorator):
    def __init__(self) -> None:
        self.elapsed_ms: float = 0.0
        self._t0: float = 0.0

    def __enter__(self) -> "Timer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        self.elapsed_ms = (time.perf_counter() - self._t0) * 1000.0


def timed(fn: Callable) -> Callable:
    """同步函数装饰器: 额外返回 `(result, elapsed_ms)`."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        result = fn(*args, **kwargs)
        return result, (time.perf_counter() - t0) * 1000.0

    return wrapper
