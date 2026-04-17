"""并行模式 (论文 4.3.4): asyncio.gather + asyncio.wait_for.

超时策略 (阶段 2 最简实现, 阶段 5 再接入三级超时容错):
  - 每个 agent 各自 `wait_for(agent.analyze(case), timeout=timeout_s)`.
  - 超时/异常视为该科室 absent, 返回 None 由调用方 (协调器) 决定是否重试.
R8: 禁止使用线程池, 只用 asyncio 原语.
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from app.schemas.case import CaseSummary
from app.schemas.opinion import DepartmentOpinion
from app.utils.logger import get_logger, log_with

_LOG = get_logger("modes.parallel")


async def _run_one(agent, case: CaseSummary, timeout_s: float) -> Optional[DepartmentOpinion]:
    try:
        return await asyncio.wait_for(agent.analyze(case), timeout=timeout_s)
    except asyncio.TimeoutError:
        log_with(_LOG, "warning", "agent timeout", dept=getattr(agent, "dept", "?"), timeout_s=timeout_s)
        return None
    except Exception as e:  # noqa: BLE001
        log_with(_LOG, "error", "agent failed", dept=getattr(agent, "dept", "?"), err=str(e))
        return None


async def run_parallel(
    agents: list,
    case: CaseSummary,
    timeout_s: float = 60,
) -> List[DepartmentOpinion]:
    """并发执行所有 agent, 过滤掉超时/失败项后返回."""
    if not agents:
        return []
    results = await asyncio.gather(*(_run_one(a, case, timeout_s) for a in agents))
    return [r for r in results if r is not None]
