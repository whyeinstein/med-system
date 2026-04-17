"""阶段 3: 安全审查单测 (论文 4.3.6).

验证 R11 三步:
  1) 定向替换风险表述
  2) 保留非风险结构
  3) 追加免责声明 (enhanced 版本在命中高风险或 L3 时生效)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.safety_agent import SafetyAgent  # noqa: E402
from app.safety.rule_engine import SafetyChecker  # noqa: E402
from app.schemas.opinion import DepartmentOpinion  # noqa: E402
from app.schemas.report import FinalReport  # noqa: E402

RULES = str(ROOT / "config" / "safety_rules.yaml")


def _op(dept: str, **kw) -> DepartmentOpinion:
    return DepartmentOpinion(
        dept=dept,
        diagnosis=kw.get("diagnosis", "普通诊断"),
        differential=kw.get("differential", "鉴别要点"),
        treatment=kw.get("treatment", "建议对症处理"),
        attention=kw.get("attention", "关注生命体征"),
        self_confidence=kw.get("self_confidence", "medium"),  # type: ignore[arg-type]
        inference_meta={},
    )


def _report(summary: str, ops: list[DepartmentOpinion], level: int = 1) -> FinalReport:
    return FinalReport(
        summary=summary,
        dept_opinions=ops,
        aggregation_level=level,
        safety_action="pass",
        disclaimer="",
    )


@pytest.fixture
def checker() -> SafetyChecker:
    return SafetyChecker(RULES, low_risk_threshold=2)


def test_rule_engine_detects_high_risk(checker: SafetyChecker) -> None:
    report = _report("患者确诊为急性阑尾炎, 需立即手术.", [_op("surgery")])
    info = checker.check(report)
    assert info["high_risk"] is True
    cats = {h["category"] for h in info["hits"]}
    assert "strong_assertion" in cats  # "确诊"
    assert "overreach" in cats  # "立即手术"


def test_rule_engine_clean_report_passes(checker: SafetyChecker) -> None:
    report = _report("综合考虑, 建议完善检查", [_op("internal", diagnosis="考虑肺部感染")])
    info = checker.check(report)
    assert info["high_risk"] is False


def test_safety_agent_full_flow_degrades_and_appends_disclaimer(
    checker: SafetyChecker,
) -> None:
    agent = SafetyAgent(checker)
    op = _op("surgery", treatment="立即手术, 给予阿莫西林 500mg/次")
    report = _report("患者确诊为急性阑尾炎", [op])
    out = agent.review(report)

    # 1) 风险词被替换
    assert "确诊" not in out.summary
    assert "建议进一步检查以明确" in out.summary
    # 2) 非风险结构保留 (仍有诊断字段与科室意见结构)
    assert len(out.dept_opinions) == 1
    assert out.dept_opinions[0].dept == "surgery"
    # dept_opinion 内部风险词也被替换
    assert "立即手术" not in out.dept_opinions[0].treatment
    assert "500mg" not in out.dept_opinions[0].treatment
    # 3) 追加免责声明 (enhanced, 因为命中高风险)
    assert out.disclaimer
    assert "安全审查" in out.disclaimer or "免责" in out.disclaimer
    assert out.safety_action == "degraded"


def test_safety_agent_pass_through_when_clean(checker: SafetyChecker) -> None:
    agent = SafetyAgent(checker)
    # 避免出现"考虑/可能/疑似"等低危软断言词, 以免触发 accumulated_high
    report = _report("建议完善检查与随访", [_op("internal", diagnosis="肺部感染待查")])
    out = agent.review(report)
    assert out.safety_action == "pass"
    assert out.disclaimer  # 放行也要附常规免责声明
    assert out.summary == "建议完善检查与随访"


def test_safety_agent_enhanced_disclaimer_for_l3(checker: SafetyChecker) -> None:
    """L3 仲裁即使无风险词也要用 enhanced 模板 (强调存在分歧)."""
    agent = SafetyAgent(checker)
    report = _report("仲裁综合意见", [_op("internal"), _op("surgery")], level=3)
    out = agent.review(report)
    # enhanced 模板中包含 "分歧" / "面诊" 之类加强表述
    assert "分歧" in out.disclaimer or "面诊" in out.disclaimer or "已经过" in out.disclaimer
