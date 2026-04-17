"""会诊协调器. 阶段 4 线性流程; 阶段 5 重构为状态机驱动.

**关键约束**:
  1. 数据库只由协调器管. 其他模块不准直连 DB.
  2. 仲裁动作发起方必须是协调器 (rank_hint=max(rank_bins)).
  3. 两层专家软对应, 不得在 prompt 中传"激活第 X 号专家".
"""
from __future__ import annotations

from typing import Dict

from app.schemas.case import CaseSummary
from app.schemas.opinion import DepartmentOpinion
from app.schemas.report import FinalReport
from app.schemas.routing import RoutingResult


class ConsultationOrchestrator:
    def __init__(
        self,
        router,
        agents_map: Dict,
        mode_runners: Dict,
        aggregator,
        safety_agent,
        storage,
        model,
        state_machine=None,
        task_queue=None,
    ) -> None:
        self.router = router
        self.agents_map = agents_map
        self.mode_runners = mode_runners
        self.aggregator = aggregator
        self.safety_agent = safety_agent
        self.storage = storage
        self.model = model
        self.state_machine = state_machine
        self.task_queue = task_queue

    async def run(self, session_id: str, case: CaseSummary) -> FinalReport:
        """阶段 4 实现线性流程; 阶段 5 改为状态机驱动."""
        raise NotImplementedError("Phase 4")

    async def _arbitrate(
        self,
        opinions: list,
        routing: RoutingResult,
    ) -> str:
        """阶段 3 末尾补: 用 rank_hint=max(rank_bins) 调用模型获得仲裁稿."""
        raise NotImplementedError("Phase 3")
