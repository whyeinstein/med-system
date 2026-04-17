"""阶段 3: 安全审查智能体 (论文 4.3.6). 串起 rule_engine → degrader → disclaimer.

R11 三步:
  1) 命中风险 → 定向替换风险表述 (degrader)
  2) 保留非风险结构 (degrader 只替换风险词)
  3) 追加免责声明, 命中高风险/分歧时用 enhanced 版本
"""
from __future__ import annotations

from app.safety.degrader import degrade
from app.safety.disclaimer import append_disclaimer
from app.safety.rule_engine import SafetyChecker
from app.schemas.report import FinalReport
from app.utils.logger import get_logger, log_with

_LOG = get_logger("agents.safety")


class SafetyAgent:
    def __init__(self, rule_engine: SafetyChecker) -> None:
        self.rule_engine = rule_engine

    def review(self, report: FinalReport) -> FinalReport:
        info = self.rule_engine.check(report)
        hit_high = info["high_risk"] or info["accumulated_high"]
        log_with(
            _LOG,
            "info",
            "safety check",
            high_risk=info["high_risk"],
            low_risk_count=info["low_risk_count"],
            arbitrated=(report.aggregation_level == 3),
        )
        out = report
        if hit_high:
            out = degrade(out, info["hits"], rules=self.rule_engine.high_rules)
        enhanced = hit_high or report.aggregation_level == 3
        out = append_disclaimer(
            out,
            enhanced=enhanced,
            template=self.rule_engine.disclaimer_template,
            enhanced_template=self.rule_engine.enhanced_disclaimer_template,
        )
        return out

