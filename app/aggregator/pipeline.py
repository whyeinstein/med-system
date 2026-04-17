"""三级递进调度器 (论文 4.3.5).

L1 pass → level=1; L1 fail & (最低余弦 >= tau_arbitrate) → level=2 走 L2 加权;
否则触发 L3: `await coordinator_hook(opinions, routing) -> str` 由协调器以 max rank_hint
调 model.generate, 本模块再用返回的 arbitrated_text 组装报告.

R2: 本模块**不直接**调模型、不读写 DB. 所有模型调用由协调器通过 hook 完成.
"""
from __future__ import annotations

from typing import Awaitable, Callable, List, Optional, Tuple

from app.aggregator.level1_consistency import consistency_check
from app.aggregator.level2_weighted import compute_weights, weighted_merge
from app.aggregator.level3_arbitration import arbitrate
from app.schemas.opinion import DepartmentOpinion
from app.schemas.report import FinalReport
from app.schemas.routing import RoutingResult
from app.utils.logger import get_logger, log_with

_LOG = get_logger("aggregator.pipeline")

CoordinatorHook = Callable[[List[DepartmentOpinion], RoutingResult], Awaitable[str]]


class AggregationPipeline:
    def __init__(
        self,
        embedder,
        tau_consist: float = 0.75,
        alpha: float = 1 / 3,
        beta: float = 1 / 3,
        gamma: float = 1 / 3,
        tau_arbitrate: float = 0.5,
    ) -> None:
        self.embedder = embedder
        self.tau_consist = tau_consist
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        # 低于此最小余弦视为严重分歧, 跳过 L2 直接进 L3 仲裁
        self.tau_arbitrate = tau_arbitrate

    async def aggregate(
        self,
        opinions: List[DepartmentOpinion],
        routing: RoutingResult,
        coordinator_hook: Optional[CoordinatorHook] = None,
    ) -> Tuple[FinalReport, int]:
        """三级递进. 返回 (report, level)."""
        if not opinions:
            empty = FinalReport(
                summary="(无可用科室意见)",
                dept_opinions=[],
                aggregation_level=1,
                safety_action="pass",
                disclaimer="",
            )
            return empty, 1

        # ---------- L1 ----------
        passed, s_min = consistency_check(opinions, self.embedder, self.tau_consist)
        log_with(_LOG, "info", "L1 consistency", passed=passed, s_min=round(s_min, 4))
        if passed:
            summary = self._l1_summary(opinions)
            return (
                FinalReport(
                    summary=summary,
                    dept_opinions=list(opinions),
                    aggregation_level=1,
                    safety_action="pass",
                    disclaimer="",
                ),
                1,
            )

        # ---------- L2 ----------
        if s_min >= self.tau_arbitrate:
            summary = weighted_merge(
                opinions, routing, self.alpha, self.beta, self.gamma
            )
            weights = compute_weights(
                opinions, routing, self.alpha, self.beta, self.gamma
            )
            log_with(_LOG, "info", "L2 weighted", weights=weights)
            return (
                FinalReport(
                    summary=summary,
                    dept_opinions=list(opinions),
                    aggregation_level=2,
                    safety_action="pass",
                    disclaimer="",
                ),
                2,
            )

        # ---------- L3 ----------
        arbitrated_text = ""
        if coordinator_hook is not None:
            # R5: 必须由协调器以 rank_hint=max(rank_bins) 调模型
            arbitrated_text = await coordinator_hook(opinions, routing)
        else:
            log_with(_LOG, "warning", "L3 triggered without coordinator_hook")
        summary = arbitrate(opinions, arbitrated_text)
        return (
            FinalReport(
                summary=summary,
                dept_opinions=list(opinions),
                aggregation_level=3,
                safety_action="arbitrated",
                disclaimer="",
            ),
            3,
        )

    @staticmethod
    def _l1_summary(opinions: List[DepartmentOpinion]) -> str:
        """L1 通过时以首条意见为主干, 附其他科室补充."""
        lead = opinions[0]
        lines = [
            f"【一致性综合意见 · 主导科室: {lead.dept}】",
            f"诊断倾向: {lead.diagnosis}",
            f"鉴别要点: {lead.differential}",
            f"处置建议: {lead.treatment}",
            f"关注事项: {lead.attention}",
        ]
        if len(opinions) > 1:
            lines.append("\n【其他科室同向意见】")
            for op in opinions[1:]:
                lines.append(f"- [{op.dept}] {op.diagnosis}")
        return "\n".join(lines)

