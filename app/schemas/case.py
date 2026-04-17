"""病例摘要. 对应论文 4.3.1 会诊协调器输入."""
from pydantic import BaseModel, Field


class CaseSummary(BaseModel):
    case_id: str = Field(..., description="病例唯一 id, 通常与 session_id 一一对应")
    chief_complaint: str = Field(..., description="主诉")
    symptoms: str = Field(..., description="症状描述")
    medical_history: str = Field("", description="既往史")
    exam_results: str = Field("", description="检查结果")
