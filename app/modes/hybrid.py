"""混合模式 (论文 4.3.4): 核心组并发 → 辅助组按需激活.

"按需"策略 (阶段 2 实现):
  核心组意见中 `self_confidence=low` 或诊断字段为空视为需要辅助; 当 >=1/3 的核心意见需要辅助,
  就把辅助组并发跑一遍补齐, 否则跳过以节约推理成本 (论文 4.2 计算效率优化动机).
"""
from __future__ import annotations

from typing import List

from app.modes.parallel import run_parallel
from app.schemas.case import CaseSummary
from app.schemas.opinion import DepartmentOpinion
from app.utils.logger import get_logger, log_with

_LOG = get_logger("modes.hybrid")


def _needs_aux(opinions: List[DepartmentOpinion]) -> bool:
    if not opinions:
        return True
    weak = sum(1 for o in opinions if o.self_confidence == "low" or not o.diagnosis)
    return weak * 3 >= len(opinions)  # weak/total >= 1/3


async def run_hybrid(
    core_agents: list,
    aux_agents: list,
    case: CaseSummary,
    timeout_s: float = 60,
) -> List[DepartmentOpinion]:
    core_ops = await run_parallel(core_agents, case, timeout_s=timeout_s)
    log_with(_LOG, "info", "hybrid core done", n_core=len(core_ops))
    if aux_agents and _needs_aux(core_ops):
        aux_ops = await run_parallel(aux_agents, case, timeout_s=timeout_s)
        log_with(_LOG, "info", "hybrid aux activated", n_aux=len(aux_ops))
        return core_ops + aux_ops
    return core_ops
