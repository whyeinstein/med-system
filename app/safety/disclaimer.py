"""免责声明: 固定模板, 不走 LLM (R11).

enhanced=True 时追加"已作安全处理/存在分歧, 建议优先就医"的加强模板.
默认模板由 SafetyAgent 从 config/safety_rules.yaml 读到后注入.
"""
from __future__ import annotations

from app.schemas.report import FinalReport


def append_disclaimer(
    report: FinalReport,
    enhanced: bool = False,
    template: str = "",
    enhanced_template: str = "",
) -> FinalReport:
    body = enhanced_template if enhanced and enhanced_template else template
    if not body:
        # 最低兜底模板
        body = "【免责声明】本报告由 AI 辅助会诊系统生成, 仅供参考, 不构成诊断或处方依据."
    return report.model_copy(update={"disclaimer": body.strip()})

