"""L2 三因子加权: w_i = α*relevance + β*confidence + γ*completeness (论文 4.3.5 第二级).

R6: relevance / confidence 不重算, 直接读 RoutingResult + DepartmentOpinion.
  - relevance_i = RoutingResult.candidates[dept_i].confidence
  - confidence_i = self_confidence 映射 {high:1.0, medium:0.6, low:0.3}
  - completeness_i = parser.completeness_score(五字段覆盖度)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.schemas.opinion import DepartmentOpinion
from app.schemas.routing import RoutingResult
from app.utils.parser import completeness_score

_CONF_MAP = {"high": 1.0, "medium": 0.6, "low": 0.3}


@dataclass
class _Weighted:
    opinion: DepartmentOpinion
    weight: float
    relevance: float
    confidence: float
    completeness: float


def _score(
    op: DepartmentOpinion,
    routing: RoutingResult,
    alpha: float,
    beta: float,
    gamma: float,
) -> _Weighted:
    relevance = 0.0
    for c in routing.candidates:
        if c.dept == op.dept:
            relevance = float(c.confidence)
            break
    confidence = _CONF_MAP.get(op.self_confidence, 0.6)
    completeness = completeness_score(
        {
            "diagnosis": op.diagnosis,
            "differential": op.differential,
            "treatment": op.treatment,
            "attention": op.attention,
            "self_confidence": op.self_confidence,
        }
    )
    weight = alpha * relevance + beta * confidence + gamma * completeness
    return _Weighted(op, weight, relevance, confidence, completeness)


def weighted_merge(
    opinions: List[DepartmentOpinion],
    routing: RoutingResult,
    alpha: float,
    beta: float,
    gamma: float,
) -> str:
    """按加权降序, 以权重最高科室为主干, 附低权重科室的补充. 返回 summary 文本."""
    if not opinions:
        return ""
    scored = [_score(op, routing, alpha, beta, gamma) for op in opinions]
    scored.sort(key=lambda s: s.weight, reverse=True)
    lead = scored[0]
    lines = [
        f"【加权综合意见 · 主导科室: {lead.opinion.dept} (w={lead.weight:.3f})】",
        f"诊断倾向: {lead.opinion.diagnosis}",
        f"鉴别要点: {lead.opinion.differential}",
        f"处置建议: {lead.opinion.treatment}",
        f"关注事项: {lead.opinion.attention}",
    ]
    if len(scored) > 1:
        lines.append("\n【其他科室补充】")
        for s in scored[1:]:
            lines.append(
                f"- [{s.opinion.dept} w={s.weight:.3f}] 诊断: {s.opinion.diagnosis}; "
                f"处置: {s.opinion.treatment}"
            )
    return "\n".join(lines)


def compute_weights(
    opinions: List[DepartmentOpinion],
    routing: RoutingResult,
    alpha: float,
    beta: float,
    gamma: float,
) -> List[dict]:
    """便于 pipeline 判定 L2 是否足以形成共识: 返回按权重降序的明细."""
    scored = [_score(op, routing, alpha, beta, gamma) for op in opinions]
    scored.sort(key=lambda s: s.weight, reverse=True)
    return [
        {
            "dept": s.opinion.dept,
            "weight": round(s.weight, 4),
            "relevance": round(s.relevance, 4),
            "confidence": round(s.confidence, 4),
            "completeness": round(s.completeness, 4),
        }
        for s in scored
    ]

