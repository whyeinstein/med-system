"""阶段 2: DepartmentAgent 单测.

不依赖 FAISS / 嵌入模型. 使用 mock ModelEngine + retriever=None.
验证:
  1) analyze() 产出 DepartmentOpinion, 五字段完整.
  2) prompt 中不出现 "激活第" "专家号" 等违规指令 (R4 软对应).
  3) context (前序意见) 能被写入 prompt.
  4) inference_meta 保存了 rank/router_weights/elapsed_ms (R10).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.department_agent import DepartmentAgent  # noqa: E402
from app.model.inference import ModelEngine  # noqa: E402
from app.schemas.case import CaseSummary  # noqa: E402


@pytest.fixture
def case() -> CaseSummary:
    return CaseSummary(
        case_id="c1",
        chief_complaint="转移性右下腹痛伴发热",
        symptoms="上腹隐痛数小时后转移至右下腹, 伴低热恶心",
        medical_history="既往体健",
        exam_results="血象升高",
    )


@pytest.fixture
def model() -> ModelEngine:
    return ModelEngine(mock=True)


def _make_agent(dept: str, model: ModelEngine) -> DepartmentAgent:
    return DepartmentAgent(dept=dept, config={}, model=model, retriever=None)


@pytest.mark.asyncio
async def test_analyze_produces_full_opinion(case: CaseSummary, model: ModelEngine) -> None:
    agent = _make_agent("surgery", model)
    op = await agent.analyze(case)
    assert op.dept == "surgery"
    for field in ("diagnosis", "differential", "treatment", "attention"):
        assert getattr(op, field), f"{field} 不应为空"
    assert op.self_confidence in {"high", "medium", "low"}
    # R10: inference_meta 必须记录关键字段
    meta = op.inference_meta
    assert "rank" in meta and meta["rank"] is not None
    assert "router_weights" in meta and meta["router_weights"]
    assert "elapsed_ms" in meta
    assert "raw_text" in meta


@pytest.mark.asyncio
async def test_prompt_has_no_expert_activation_phrases(
    case: CaseSummary, model: ModelEngine
) -> None:
    """R4: 严禁在 prompt 中出现"激活第 X 号专家 / 使用科室 Y 的路由"等指令."""
    agent = _make_agent("internal", model)
    prompt = agent._build_prompt(case, retrieved=[], context=None)
    banned = ["激活第", "专家号", "第 1 号专家", "第1号专家", "使用科室", "路由到专家"]
    for phrase in banned:
        assert phrase not in prompt, f"prompt 含违规指令: {phrase}"
    # 应包含科室 display 与病例主诉
    assert "内科" in prompt
    assert case.chief_complaint in prompt


@pytest.mark.asyncio
async def test_serial_context_injected(case: CaseSummary, model: ModelEngine) -> None:
    agent = _make_agent("pediatrics", model)
    prompt = agent._build_prompt(case, retrieved=[], context="[internal] 诊断倾向: 上感可能")
    assert "前序会诊意见" in prompt
    assert "[internal]" in prompt
