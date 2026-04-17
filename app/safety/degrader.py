"""降级输出 (论文 4.3.6): 定向替换风险表述, 保留结构与非风险内容.

R11 三步之第一步. 替换规则从 SafetyChecker.high_rules 读取 (pattern, replacement).
"""
from __future__ import annotations

import re
from typing import List, Pattern, Tuple

from app.schemas.opinion import DepartmentOpinion
from app.schemas.report import FinalReport


def _apply(patterns: List[Tuple[Pattern, str]], text: str) -> str:
    if not text:
        return text
    out = text
    for pat, repl in patterns:
        out = pat.sub(repl, out)
    return out


def degrade(report: FinalReport, hits: list, rules: List[dict] | None = None) -> FinalReport:
    """根据 high_risk_rules 对报告做定向替换. hits 仅用于日志, 真正替换用 rules.

    rules 期望每项为 `{"pattern": re.Pattern, "replacement": str, ...}`, 兼容 SafetyChecker.high_rules.
    为了向后兼容, 当未传 rules 时从 hits[i]["pattern"] + 默认替换重建 (低配版).
    """
    if rules is None:
        # 兜底: 用 hits 中的原始 pattern + 通用替换
        rules = [
            {"pattern": re.compile(h["pattern"]), "replacement": "[已脱敏]"}
            for h in hits
        ]
    compiled: List[Tuple[Pattern, str]] = [(r["pattern"], r["replacement"]) for r in rules]

    new_summary = _apply(compiled, report.summary)
    new_opinions: List[DepartmentOpinion] = []
    for op in report.dept_opinions:
        new_opinions.append(
            op.model_copy(
                update={
                    "diagnosis": _apply(compiled, op.diagnosis),
                    "differential": _apply(compiled, op.differential),
                    "treatment": _apply(compiled, op.treatment),
                    "attention": _apply(compiled, op.attention),
                }
            )
        )
    return report.model_copy(
        update={
            "summary": new_summary,
            "dept_opinions": new_opinions,
            "safety_action": "degraded" if report.safety_action == "pass" else report.safety_action,
        }
    )

