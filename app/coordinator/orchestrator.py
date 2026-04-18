"""会诊协调器 (论文 4.3.1). 阶段 4 线性流程; 阶段 5 重构为状态机驱动.

**关键约束**:
  R2  数据库**只**由协调器读写, 通过本类持有的 `StorageBundle` 完成.
  R5  仲裁动作发起方**必须**是协调器: `_arbitrate` 显式以 `rank_hint=max(rank_bins)`
      调 `model.generate`, 把仲裁稿回传给 aggregator 的 L3 组装函数.
  R8  同步推理 ( `model.generate` / `router.route` ) 经 `asyncio.to_thread` 包装.
  R10 routing / opinion / report 三段产出全部写入 `message` 表, 含完整 `inference_meta`,
      为 4.5.6 案例分析与专家分化可视化提供唯一数据源.

消融开关 (论文 4.5.5, 通过环境变量或显式构造参数控制):
  - use_router=False  → 跳过 router, 退化为"全科室并行"
  - use_hybrid=False  → 不使用 hybrid 模式, 多科室时退化为 parallel
  - use_safety=False  → 跳过 SafetyAgent.review
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.modes.hybrid import run_hybrid
from app.modes.mode_selector import select_mode
from app.modes.parallel import run_parallel
from app.modes.serial import run_serial
from app.schemas.case import CaseSummary
from app.schemas.opinion import DepartmentOpinion
from app.schemas.report import FinalReport
from app.schemas.routing import DeptCandidate, RoutingResult
from app.storage.case_repo import CaseRepo
from app.storage.message_repo import MessageRepo
from app.storage.session_repo import SessionRepo
from app.utils.logger import get_logger, log_with
from app.utils.timer import Timer

_LOG = get_logger("coordinator.orchestrator")


@dataclass
class StorageBundle:
    """三个 repo 的聚合, 只交给协调器持有 (R2)."""

    session: SessionRepo
    case: CaseRepo
    message: MessageRepo


class ConsultationOrchestrator:
    def __init__(
        self,
        router,
        agents_map: Dict[str, object],
        aggregator,
        safety_agent,
        storage: StorageBundle,
        model,
        *,
        timeout_s: float = 60.0,
        mode_thresholds: Optional[dict] = None,
        use_router: bool = True,
        use_hybrid: bool = True,
        use_safety: bool = True,
        default_mode: str = "parallel",
        state_machine=None,
        task_queue=None,
    ) -> None:
        self.router = router
        self.agents_map = dict(agents_map)
        self.aggregator = aggregator
        self.safety_agent = safety_agent
        self.storage = storage
        self.model = model
        self.timeout_s = float(timeout_s)
        self.mode_thresholds = dict(mode_thresholds or {})
        self.use_router = use_router
        self.use_hybrid = use_hybrid
        self.use_safety = use_safety
        self.default_mode = default_mode
        # 阶段 5 接入
        self.state_machine = state_machine
        self.task_queue = task_queue

    # ============================================================
    # 主流程
    # ============================================================

    async def run(self, session_id: str, case: CaseSummary) -> FinalReport:
        """阶段 4 线性流程: case → routing → mode → agents → aggregator → safety.

        每一步的产出都通过 `MessageRepo` 落库 (R2 + R10), 为后续可视化与回溯提供数据.
        """
        round_ = 1
        # 0. 病例落库 (R2: 仅协调器写)
        self.storage.case.create(session_id, case)
        log_with(_LOG, "info", "consultation start", session_id=session_id, case_id=case.case_id)

        # 1. 路由
        routing = await self._do_routing(case)
        self._save_routing(session_id, routing, round_)

        # 2. 模式选择 + 调度执行
        mode = self._pick_mode(routing)
        log_with(_LOG, "info", "mode picked", session_id=session_id, mode=mode, triage=routing.triage_tag)
        with Timer() as t_mode:
            opinions = await self._dispatch_mode(mode, case, routing)
        log_with(
            _LOG, "info", "agents done",
            session_id=session_id, mode=mode, n_opinions=len(opinions),
            elapsed_ms=round(t_mode.elapsed_ms, 2),
        )
        self._save_opinions(session_id, opinions, round_)

        # 3. 三级综合 (含 L3 仲裁回调)
        report, level = await self.aggregator.aggregate(
            opinions, routing, coordinator_hook=self._arbitrate
        )

        # 4. 安全审查
        if self.use_safety:
            report = self.safety_agent.review(report)
        else:
            log_with(_LOG, "info", "safety skipped (ablation)", session_id=session_id)

        # 5. 报告落库
        self._save_report(session_id, report, level, mode, round_)

        log_with(
            _LOG, "info", "consultation done",
            session_id=session_id, agg_level=level, safety_action=report.safety_action,
        )
        return report

    # ============================================================
    # 路由
    # ============================================================

    async def _do_routing(self, case: CaseSummary) -> RoutingResult:
        if self.use_router:
            # router.route 是同步, 走 to_thread (R8)
            return await asyncio.to_thread(self.router.route, case)
        # 消融: 全科室并行, 置信度均分
        keys = list(self.agents_map.keys())
        n = max(len(keys), 1)
        cands = [DeptCandidate(dept=k, confidence=1.0 / n) for k in keys]
        return RoutingResult(
            candidates=cands,
            triage_tag="ambiguous",
            fallback_triggered=False,
            retrieval_hits=[],
        )

    # ============================================================
    # 模式选择 + 调度
    # ============================================================

    def _pick_mode(self, routing: RoutingResult) -> str:
        if not self.use_router:
            return self.default_mode
        mode = select_mode(routing, self.mode_thresholds)
        if mode == "hybrid" and not self.use_hybrid:
            return "parallel"
        return mode

    async def _dispatch_mode(
        self, mode: str, case: CaseSummary, routing: RoutingResult
    ) -> List[DepartmentOpinion]:
        candidate_keys = [c.dept for c in routing.candidates if c.confidence > 0]
        all_agents = [self.agents_map[k] for k in candidate_keys if k in self.agents_map]

        if mode == "serial":
            # single_clear 时仅以 top1 走串行 (兼顾"快路径")
            top_key = routing.candidates[0].dept if routing.candidates else None
            if top_key and top_key in self.agents_map:
                chosen = [self.agents_map[top_key]]
            else:
                chosen = all_agents
            return await run_serial(chosen, case, timeout_s=self.timeout_s)

        if mode == "hybrid":
            core_min = float(self.mode_thresholds.get("hybrid_core_min_conf", 0.2))
            core_keys = [c.dept for c in routing.candidates if c.confidence >= core_min]
            aux_keys = [k for k in candidate_keys if k not in core_keys]
            core = [self.agents_map[k] for k in core_keys if k in self.agents_map]
            aux = [self.agents_map[k] for k in aux_keys if k in self.agents_map]
            return await run_hybrid(core, aux, case, timeout_s=self.timeout_s)

        # parallel (含 ambiguous)
        return await run_parallel(all_agents, case, timeout_s=self.timeout_s)

    # ============================================================
    # 仲裁回调 (R5 核心亮点)
    # ============================================================

    async def _arbitrate(
        self,
        opinions: List[DepartmentOpinion],
        routing: RoutingResult,
    ) -> str:
        """L3 命中时由 aggregator 回调本方法.

        协调器以 `rank_hint=max(self.model.rank_bins)` 显式调模型, 让仲裁推理在
        最高秩档位 (参数容量更充足) 下处理多源冲突. 这是论文 4.3.5 第三级 +
        4.3.1 "系统层与模型层协同"的核心亮点, 严禁删除显式的 rank_hint=max(...).
        """
        prompt = self._build_arbitration_prompt(opinions, routing)
        max_rank = max(self.model.rank_bins)
        text, meta = await asyncio.to_thread(
            self.model.generate, prompt, rank_hint=max_rank  # R5: 必须显式 max
        )
        log_with(
            _LOG, "info", "arbitration done",
            rank=meta.get("rank"), elapsed_ms=meta.get("elapsed_ms"),
            n_opinions=len(opinions),
        )
        return text

    @staticmethod
    def _build_arbitration_prompt(
        opinions: List[DepartmentOpinion], routing: RoutingResult
    ) -> str:
        """构造仲裁 prompt. 仅注入科室名 + 各意见五字段, 不出现"激活第 X 号专家" (R4)."""
        lines = [
            "你是医疗会诊仲裁角色. 以下来自多个科室专家的会诊意见存在显著分歧, "
            "请基于循证医学综合分析后, 给出明确的诊断倾向、鉴别要点、处置建议与关注事项, "
            "并对存在的不确定性予以提示.\n",
        ]
        for op in opinions:
            lines.append(f"## 来自 [{op.dept}] (自评置信度: {op.self_confidence})")
            lines.append(f"诊断倾向: {op.diagnosis}")
            lines.append(f"鉴别要点: {op.differential}")
            lines.append(f"处置建议: {op.treatment}")
            lines.append(f"关注事项: {op.attention}\n")
        if routing and routing.candidates:
            cand_brief = ", ".join(
                f"{c.dept}={c.confidence:.2f}" for c in routing.candidates
            )
            lines.append(f"路由置信度参考: {cand_brief}\n")
        lines.append(
            "请按以下格式输出综合意见:\n"
            "诊断倾向: ...\n"
            "鉴别要点: ...\n"
            "处置建议: ...\n"
            "关注事项: ...\n"
            "自评置信度: high/medium/low\n"
        )
        return "\n".join(lines)

    # ============================================================
    # 落库辅助 (R2: 仅本类直接调 MessageRepo)
    # ============================================================

    def _save_routing(self, sid: str, routing: RoutingResult, round_: int) -> None:
        self.storage.message.add(
            sid,
            role="routing",
            payload=routing.model_dump(),
            inference_meta={
                "triage_tag": routing.triage_tag,
                "fallback_triggered": routing.fallback_triggered,
                "n_candidates": len(routing.candidates),
                "n_retrieval_hits": len(routing.retrieval_hits),
            },
            round_=round_,
        )

    def _save_opinions(
        self, sid: str, opinions: List[DepartmentOpinion], round_: int
    ) -> None:
        for op in opinions:
            self.storage.message.add(
                sid,
                role="opinion",
                payload=op.model_dump(),
                inference_meta=op.inference_meta,  # R10: 全量 rank/router_weights/elapsed_ms
                round_=round_,
            )

    def _save_report(
        self,
        sid: str,
        report: FinalReport,
        level: int,
        mode: str,
        round_: int,
    ) -> None:
        self.storage.message.add(
            sid,
            role="report",
            payload=report.model_dump(),
            inference_meta={
                "aggregation_level": level,
                "safety_action": report.safety_action,
                "mode": mode,
                "n_opinions": len(report.dept_opinions),
            },
            round_=round_,
        )
