"""串行模式 (论文 4.3.4): 前序意见写回 context 后再喂给下一个 agent.

适用于 single_clear 或明确需要逐级会诊的场景. 超时一次即视为该科室 absent, 继续后续科室.
"""
from __future__ import annotations

import asyncio
from typing import List

from app.schemas.case import CaseSummary
from app.schemas.opinion import DepartmentOpinion
from app.utils.logger import get_logger, log_with

_LOG = get_logger("modes.serial")


def _format_prior(opinions: List[DepartmentOpinion]) -> str:
    """将前序意见压缩为简短上下文, 只保留核心字段避免 prompt 爆炸."""
    blocks = []
    for op in opinions:
        blocks.append(
            f"[{op.dept}] 诊断倾向: {op.diagnosis}\n"
            f"         鉴别要点: {op.differential}\n"
            f"         处置建议: {op.treatment}\n"
            f"         自评置信度: {op.self_confidence}"
        )
    return "\n".join(blocks)


async def run_serial(
    agents: list,
    case: CaseSummary,
    timeout_s: float = 60,
) -> List[DepartmentOpinion]:
    opinions: List[DepartmentOpinion] = []
    for agent in agents:
        context = _format_prior(opinions) if opinions else None
        try:
            op = await asyncio.wait_for(agent.analyze(case, context=context), timeout=timeout_s)
            opinions.append(op)
        except asyncio.TimeoutError:
            log_with(_LOG, "warning", "agent timeout", dept=getattr(agent, "dept", "?"))
        except Exception as e:  # noqa: BLE001
            log_with(_LOG, "error", "agent failed", dept=getattr(agent, "dept", "?"), err=str(e))
    return opinions
