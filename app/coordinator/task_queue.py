"""任务队列 + 三级超时容错 (论文 4.3.1 协调器子模块).

替换阶段 2~4 在 ``app/modes/parallel.py`` 中的"单层 ``asyncio.wait_for`` + 静默丢弃"
策略, 提供更鲁棒的故障恢复:

    L1 重试       每个任务独立带超时, 失败/超时后允许 ``max_retries`` 次重试;
    L2 缺席标注   重试耗尽后将该任务标 ``status="absent"``, 不阻塞其他并发任务;
    L3 全局降级   当 ``absent / total >= degrade_ratio`` 时置 ``degraded=True``,
                  由协调器决定是否进入 Error 状态或走兜底报告路径.

R8: 仅使用 ``asyncio`` 原语, 严禁 ``threading``.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List, Optional, Tuple

from app.utils.logger import get_logger, log_with

_LOG = get_logger("coordinator.task_queue")

# 每个任务以 "无参的协程工厂" 形式提交, 便于重试时重新构造 awaitable.
CoroFactory = Callable[[], Awaitable[Any]]


@dataclass
class TaskRecord:
    label: str
    status: str = "pending"  # success / absent / pending
    attempts: int = 0
    result: Any = None
    last_error: Optional[str] = None
    elapsed_ms: float = 0.0


@dataclass
class QueueResult:
    results: List[Any] = field(default_factory=list)
    records: List[TaskRecord] = field(default_factory=list)
    absent: List[str] = field(default_factory=list)
    degraded: bool = False
    degrade_reason: Optional[str] = None

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def absent_ratio(self) -> float:
        return (len(self.absent) / self.total) if self.total else 0.0


class TaskQueue:
    """协调器使用的并发任务执行器.

    Parameters
    ----------
    timeout_s : 单次尝试超时 (秒).
    max_retries : 失败/超时后追加重试次数 (不含首次). 0 表示不重试.
    degrade_ratio : 全局降级阈值, ``absent / total`` 达到该比例即触发.
    on_degrade : 全局降级回调, 收到 ``QueueResult`` 后协调器可写日志/落 message.
    """

    def __init__(
        self,
        *,
        timeout_s: float = 60.0,
        max_retries: int = 1,
        degrade_ratio: float = 0.5,
        on_degrade: Optional[Callable[[QueueResult], None]] = None,
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if not (0.0 < degrade_ratio <= 1.0):
            raise ValueError("degrade_ratio must be in (0, 1]")
        self.timeout_s = float(timeout_s)
        self.max_retries = int(max_retries)
        self.degrade_ratio = float(degrade_ratio)
        self.on_degrade = on_degrade

    async def _run_one(self, label: str, factory: CoroFactory) -> TaskRecord:
        rec = TaskRecord(label=label)
        loop = asyncio.get_event_loop()
        for attempt in range(1, self.max_retries + 2):  # 首次 + 重试
            rec.attempts = attempt
            t0 = loop.time()
            try:
                rec.result = await asyncio.wait_for(factory(), timeout=self.timeout_s)
                rec.elapsed_ms = (loop.time() - t0) * 1000.0
                rec.status = "success"
                if attempt > 1:
                    log_with(
                        _LOG, "info", "task recovered",
                        label=label, attempts=attempt,
                    )
                return rec
            except asyncio.TimeoutError:
                rec.last_error = f"timeout after {self.timeout_s}s"
                log_with(
                    _LOG, "warning", "task timeout",
                    label=label, attempt=attempt, timeout_s=self.timeout_s,
                )
            except Exception as e:  # noqa: BLE001
                rec.last_error = f"{type(e).__name__}: {e}"
                log_with(
                    _LOG, "warning", "task error",
                    label=label, attempt=attempt, err=rec.last_error,
                )
        # L2: 重试耗尽 → 缺席标注
        rec.status = "absent"
        log_with(
            _LOG, "error", "task absent",
            label=label, attempts=rec.attempts, last_error=rec.last_error,
        )
        return rec

    async def run(self, tasks: List[Tuple[str, CoroFactory]]) -> QueueResult:
        """并发执行 ``tasks`` (label, factory). 返回三级容错聚合结果."""
        if not tasks:
            return QueueResult()

        records = await asyncio.gather(
            *(self._run_one(label, factory) for label, factory in tasks)
        )
        absent = [r.label for r in records if r.status == "absent"]
        results = [r.result for r in records if r.status == "success"]
        result = QueueResult(
            results=results,
            records=list(records),
            absent=absent,
        )
        # L3: 全局降级判定
        if result.total and (len(absent) / result.total) >= self.degrade_ratio:
            result.degraded = True
            result.degrade_reason = (
                f"{len(absent)}/{result.total} tasks absent "
                f">= degrade_ratio {self.degrade_ratio}"
            )
            log_with(
                _LOG, "error", "global degrade triggered",
                absent=absent, total=result.total, ratio=self.degrade_ratio,
            )
            if self.on_degrade:
                try:
                    self.on_degrade(result)
                except Exception:  # noqa: BLE001
                    pass
        return result
