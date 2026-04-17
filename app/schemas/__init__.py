"""数据契约: 层间消息协议 (Pydantic v2)."""
from app.schemas.case import CaseSummary
from app.schemas.routing import DeptCandidate, RoutingResult
from app.schemas.opinion import DepartmentOpinion
from app.schemas.report import FinalReport

__all__ = [
    "CaseSummary",
    "DeptCandidate",
    "RoutingResult",
    "DepartmentOpinion",
    "FinalReport",
]
