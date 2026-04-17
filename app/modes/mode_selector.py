"""依据 RoutingResult 选择会诊模式 (论文 4.3.4).

策略 (来自"下一步计划 6.2"):
  - triage_tag=single_clear  → serial   (仅 top1 科室, 快路径)
  - triage_tag=multi_cross   → hybrid   (核心组 = top-k 以内的高置信科室, 辅助组 = 其他登记科室)
                                当候选数 <= 2 时降级为 parallel (没有辅助组的必要)
  - triage_tag=ambiguous     → parallel (含 fallback 加入的 general)
"""
from __future__ import annotations

from app.schemas.routing import RoutingResult


def select_mode(routing: RoutingResult, thresholds: dict | None = None) -> str:
    """返回 'parallel' / 'serial' / 'hybrid'.

    thresholds 支持: margin (复用 router 的判定差), hybrid_core_min_conf (核心组置信下限).
    """
    thresholds = thresholds or {}
    if routing.triage_tag == "single_clear":
        return "serial"
    if routing.triage_tag == "ambiguous":
        return "parallel"
    # multi_cross
    core_min_conf = float(thresholds.get("hybrid_core_min_conf", 0.2))
    core_cnt = sum(1 for c in routing.candidates if c.confidence >= core_min_conf)
    if core_cnt >= 2 and len(routing.candidates) > core_cnt:
        return "hybrid"
    return "parallel"
