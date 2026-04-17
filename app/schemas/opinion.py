"""科室意见. 对应论文 4.3.3 科室专家智能体输出."""
from typing import Dict, Literal

from pydantic import BaseModel, Field

ConfidenceLevel = Literal["high", "medium", "low"]


class DepartmentOpinion(BaseModel):
    dept: str
    diagnosis: str = Field(..., description="诊断倾向")
    differential: str = Field(..., description="鉴别要点")
    treatment: str = Field(..., description="处置建议")
    attention: str = Field(..., description="关注事项")
    self_confidence: ConfidenceLevel
    inference_meta: Dict = Field(
        default_factory=dict,
        description="耗时/rank/router_weights 等, 供 4.5.6 案例分析与专家分化可视化",
    )
