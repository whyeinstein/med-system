"""最终报告. 对应论文 4.3.5 意见综合 + 4.3.6 安全审查后的产物."""
from typing import List, Literal

from pydantic import BaseModel, Field

from app.schemas.opinion import DepartmentOpinion

SafetyAction = Literal["pass", "degraded", "arbitrated"]


class FinalReport(BaseModel):
    summary: str = Field(..., description="综合结论")
    dept_opinions: List[DepartmentOpinion] = Field(
        default_factory=list, description="保留原始意见, 供可追溯"
    )
    aggregation_level: int = Field(..., ge=1, le=3, description="命中 L1/L2/L3")
    safety_action: SafetyAction = "pass"
    disclaimer: str = ""
