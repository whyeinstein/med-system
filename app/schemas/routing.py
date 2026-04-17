"""路由调度结果. 对应论文 4.3.2 智能路由调度器输出."""
from typing import Dict, List, Literal

from pydantic import BaseModel, Field


class DeptCandidate(BaseModel):
    dept: str = Field(..., description="科室内部 key, 如 internal/surgery/pediatrics/general")
    confidence: float = Field(..., ge=0.0, le=1.0, description="softmax 归一化后的置信度")


TriageTag = Literal["single_clear", "multi_cross", "ambiguous"]


class RoutingResult(BaseModel):
    candidates: List[DeptCandidate] = Field(..., description="按 confidence 降序")
    triage_tag: TriageTag
    fallback_triggered: bool = False
    retrieval_hits: List[Dict] = Field(
        default_factory=list,
        description="检索原始命中, 仅用于日志/解释性, 不拼入后续 agent prompt",
    )
