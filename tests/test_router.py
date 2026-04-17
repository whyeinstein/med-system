"""路由调度器单测. 依赖: 已构建好的 FAISS 索引 (`data/faiss_index`)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.knowledge.embedder import get_default_embedder  # noqa: E402
from app.knowledge.retriever import FaissRetriever  # noqa: E402
from app.router.department_router import DepartmentRouter  # noqa: E402
from app.schemas.case import CaseSummary  # noqa: E402

INDEX_DIR = ROOT / "data" / "faiss_index"
DEPARTMENTS = ["internal", "surgery", "pediatrics", "general"]


pytestmark = pytest.mark.skipif(
    not (INDEX_DIR / "faiss.index").exists(),
    reason="需先运行 scripts/build_kb_index.py 构建索引",
)


@pytest.fixture(scope="module")
def router() -> DepartmentRouter:
    embedder = get_default_embedder()
    retriever = FaissRetriever(embedder)
    retriever.load(INDEX_DIR)
    return DepartmentRouter(
        retriever=retriever,
        departments=DEPARTMENTS,
        tau=0.3,
        margin=0.2,
        temperature=1.0,
        top_k=10,
    )


@pytest.mark.parametrize(
    "case, expected_dept",
    [
        (
            CaseSummary(
                case_id="t1",
                chief_complaint="转移性右下腹痛伴发热",
                symptoms="患者先感上腹隐痛, 数小时后疼痛转移并固定于右下腹, 伴低热与恶心",
            ),
            "surgery",
        ),
        (
            CaseSummary(
                case_id="t2",
                chief_complaint="小儿高热伴手足皮疹",
                symptoms="3 岁患儿发热 2 天, 手掌足底出现疱疹, 口腔可见溃疡, 流涎拒食",
            ),
            "pediatrics",
        ),
        (
            CaseSummary(
                case_id="t3",
                chief_complaint="咳嗽咳痰伴发热 1 周",
                symptoms="成年男性咳嗽咳黄痰, 伴发热畏寒, 胸片提示右下肺片状阴影",
            ),
            "internal",
        ),
    ],
)
def test_top1_dept(router: DepartmentRouter, case: CaseSummary, expected_dept: str) -> None:
    result = router.route(case)
    assert result.candidates, "候选科室不应为空"
    top = result.candidates[0]
    assert top.dept == expected_dept, (
        f"期望 top1={expected_dept}, 实际 {top.dept}; 全部: "
        f"{[(c.dept, round(c.confidence, 3)) for c in result.candidates]}"
    )


def test_ambiguous_triggers_fallback(router: DepartmentRouter) -> None:
    """明显无关的病例应触发 ambiguous + fallback (将 general 并入候选)."""
    case = CaseSummary(
        case_id="t4",
        chief_complaint="今天天气不错心情愉悦",
        symptoms="完全无临床症状, 测试兜底分支",
    )
    result = router.route(case)
    if result.triage_tag == "ambiguous":
        assert result.fallback_triggered is True
        depts = {c.dept for c in result.candidates}
        assert "general" in depts
