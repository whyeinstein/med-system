"""路由兜底. `max(conf) < tau` 时, 把通用科室并入候选集合并重排序."""
from __future__ import annotations

from app.schemas.routing import DeptCandidate, RoutingResult


def apply_fallback(result: RoutingResult, general_dept: str = "general") -> RoutingResult:
    if not result.candidates:
        # 极端情况: 空候选 → 注入通用科室, 置信度给 1.0
        return result.model_copy(
            update={
                "candidates": [DeptCandidate(dept=general_dept, confidence=1.0)],
                "fallback_triggered": True,
            }
        )

    cands = list(result.candidates)
    existing = {c.dept for c in cands}
    if general_dept not in existing:
        # 在最低置信度之上略微提高, 保证通用科室参与后续并行推理
        min_conf = min(c.confidence for c in cands)
        cands.append(DeptCandidate(dept=general_dept, confidence=max(min_conf, 0.05)))

    cands.sort(key=lambda c: c.confidence, reverse=True)
    return result.model_copy(update={"candidates": cands, "fallback_triggered": True})
