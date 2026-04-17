"""阶段 2: 科室专家智能体.

流水: 检索参考知识 → 两步过滤 → 装配五区块 prompt → await 模型 → 解析五字段.

R3: 本层绝不触碰模型内部, 仅通过 `ModelEngine.generate` 调用.
R4: prompt 中不出现任何 "激活第 X 号专家" 之类的指令.
"""
from __future__ import annotations

from typing import Optional

from app.agents.base_agent import BaseAgent
from app.schemas.case import CaseSummary
from app.schemas.opinion import DepartmentOpinion
from app.utils.logger import get_logger, log_with
from app.utils.timer import Timer

_LOG = get_logger("agents.department")


class DepartmentAgent(BaseAgent):
    async def analyze(
        self,
        case: CaseSummary,
        context: Optional[str] = None,
    ) -> DepartmentOpinion:
        with Timer() as t:
            retrieved = self._retrieve_knowledge(case, top_k=5)
            prompt = self._build_prompt(case, retrieved, context=context)
            text, meta = await self._generate(prompt, rank_hint=None)
            opinion = self._compose_opinion(text, meta, retrieved)
        opinion.inference_meta["agent_elapsed_ms"] = round(t.elapsed_ms, 2)
        log_with(
            _LOG,
            "info",
            "agent analyzed",
            dept=self.dept,
            case_id=case.case_id,
            elapsed_ms=opinion.inference_meta["agent_elapsed_ms"],
            self_confidence=opinion.self_confidence,
            retrieved=len(retrieved),
            has_context=bool(context),
        )
        return opinion
