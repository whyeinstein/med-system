"""L3 分歧仲裁: 仅做报告组装, 不主动调模型 (论文 4.3.5 第三级).

R5: 仲裁推理由协调器以 `rank_hint=max(rank_bins)` 调 `model.generate`,
    文本再回传给本函数; 本模块只把仲裁稿与各科室原意见组装为带不确定性标注的报告.
"""
from __future__ import annotations

from typing import List

from app.schemas.opinion import DepartmentOpinion


def arbitrate(opinions: List[DepartmentOpinion], arbitrated_text: str) -> str:
    """组装仲裁后的 summary. arbitrated_text 来自协调器 (高秩档推理)."""
    lines = ["【L3 仲裁综合意见 · 已调用最高秩档推理】"]
    text = (arbitrated_text or "").strip()
    if text:
        lines.append(text)
    if opinions:
        lines.append("\n【各科室原始意见保留, 供追溯】")
        for op in opinions:
            lines.append(
                f"- [{op.dept}] 诊断: {op.diagnosis or '(缺)'}; "
                f"处置: {op.treatment or '(缺)'}; 置信: {op.self_confidence}"
            )
    lines.append("\n注: 本次会诊存在显著分歧, 上述综合意见为系统仲裁结果, 建议尽早线下面诊.")
    return "\n".join(lines)

