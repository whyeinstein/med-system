"""阶段 3: 意见综合 pipeline 单测.

使用 FakeEmbedder 构造可控的一致性场景, 不依赖真实 BGE.
验证:
  - L1 余弦最小值 (非均值) 判决
  - L1 通过 → level=1, safety_action=pass
  - L1 不过但非严重分歧 → level=2 加权
  - 严重分歧 → level=3, 触发 coordinator_hook 且得到仲裁稿
  - L2 权重公式: w = α*relevance + β*confidence + γ*completeness, relevance 读自 routing
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.aggregator.level1_consistency import consistency_check  # noqa: E402
from app.aggregator.level2_weighted import compute_weights, weighted_merge  # noqa: E402
from app.aggregator.pipeline import AggregationPipeline  # noqa: E402
from app.schemas.opinion import DepartmentOpinion  # noqa: E402
from app.schemas.routing import DeptCandidate, RoutingResult  # noqa: E402


class FakeEmbedder:
    """把指定文本映射到预设向量, 未登记的文本用字符和映射保证两两不同."""

    def __init__(self, mapping: dict[str, list[float]] | None = None) -> None:
        self.mapping = mapping or {}

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = []
        for t in texts:
            if t in self.mapping:
                v = np.array(self.mapping[t], dtype=np.float32)
            else:
                # 由字符散列出一个 4 维向量, 保证不同文本线性无关
                h = [hash((t, i)) % 1000 / 1000.0 for i in range(4)]
                v = np.array(h, dtype=np.float32)
            n = np.linalg.norm(v)
            if n > 0:
                v = v / n
            vecs.append(v)
        return np.stack(vecs, axis=0)


def _op(dept: str, dx: str, conf: str = "high", **kw) -> DepartmentOpinion:
    return DepartmentOpinion(
        dept=dept,
        diagnosis=dx,
        differential=kw.get("differential", "dd"),
        treatment=kw.get("treatment", "tx"),
        attention=kw.get("attention", "att"),
        self_confidence=conf,  # type: ignore[arg-type]
        inference_meta={},
    )


def _routing(confs: dict[str, float]) -> RoutingResult:
    cands = [DeptCandidate(dept=d, confidence=c) for d, c in confs.items()]
    return RoutingResult(candidates=cands, triage_tag="multi_cross")


# ---------------- L1 ----------------


def test_consistency_min_not_mean() -> None:
    """若 3 条意见两两余弦为 [0.9, 0.9, 0.1], 最小值=0.1 应判失败 (均值 0.63 会误判通过)."""
    v_a = [1.0, 0.0]
    v_b = [0.95, 0.312]     # 与 A 余弦 ~ 0.95
    v_c = [0.1, 0.99]       # 与 A 余弦 ~ 0.1
    embedder = FakeEmbedder({"A": v_a, "B": v_b, "C": v_c})
    ops = [_op("d1", "A"), _op("d2", "B"), _op("d3", "C")]
    passed, s_min = consistency_check(ops, embedder, tau=0.75)
    assert passed is False
    assert s_min < 0.5


def test_consistency_single_opinion_trivially_pass() -> None:
    embedder = FakeEmbedder()
    ops = [_op("d1", "A")]
    passed, s_min = consistency_check(ops, embedder, tau=0.75)
    assert passed is True
    assert s_min == pytest.approx(1.0)


# ---------------- L2 ----------------


def test_weighted_scores_use_routing_relevance() -> None:
    ops = [_op("internal", "A", conf="medium"), _op("surgery", "B", conf="high")]
    routing = _routing({"internal": 0.2, "surgery": 0.8})
    weights = compute_weights(ops, routing, alpha=1 / 3, beta=1 / 3, gamma=1 / 3)
    # surgery 的 relevance 与 confidence 都高, 应占主导
    assert weights[0]["dept"] == "surgery"
    assert weights[0]["relevance"] == pytest.approx(0.8)
    assert weights[1]["relevance"] == pytest.approx(0.2)
    # completeness 均为 1.0 (五字段全填)
    assert weights[0]["completeness"] == pytest.approx(1.0)


def test_weighted_merge_lead_is_top_weighted() -> None:
    ops = [_op("internal", "IDX", conf="low"), _op("surgery", "SDX", conf="high")]
    routing = _routing({"internal": 0.2, "surgery": 0.8})
    summary = weighted_merge(ops, routing, 1 / 3, 1 / 3, 1 / 3)
    # surgery 应为主导科室
    assert "主导科室: surgery" in summary
    assert "SDX" in summary
    assert "IDX" in summary  # 其他科室仍保留补充


# ---------------- Pipeline 三级 ----------------


@pytest.mark.asyncio
async def test_pipeline_l1_pass() -> None:
    """所有意见诊断相同 → 余弦=1 → level=1."""
    embedder = FakeEmbedder()
    ops = [_op("internal", "急性阑尾炎"), _op("surgery", "急性阑尾炎")]
    routing = _routing({"internal": 0.4, "surgery": 0.6})
    pipe = AggregationPipeline(embedder, tau_consist=0.75)
    report, level = await pipe.aggregate(ops, routing)
    assert level == 1
    assert report.aggregation_level == 1
    assert report.safety_action == "pass"
    assert "急性阑尾炎" in report.summary


@pytest.mark.asyncio
async def test_pipeline_l2_weighted_on_partial_disagreement() -> None:
    """中度分歧 (最小余弦介于 tau_arbitrate 与 tau_consist 之间) → level=2."""
    # A/B 正交 → 余弦=0; 但我们需要 mild disagreement, 让他们夹角 ~60度 → cos=0.5
    v_a = [1.0, 0.0]
    v_b = [0.6, 0.8]  # cos(A,B) = 0.6
    embedder = FakeEmbedder({"DX-A": v_a, "DX-B": v_b})
    ops = [_op("internal", "DX-A", conf="medium"), _op("surgery", "DX-B", conf="high")]
    routing = _routing({"internal": 0.3, "surgery": 0.7})
    pipe = AggregationPipeline(embedder, tau_consist=0.75, tau_arbitrate=0.5)
    report, level = await pipe.aggregate(ops, routing)
    assert level == 2
    assert report.aggregation_level == 2
    assert "主导科室: surgery" in report.summary


@pytest.mark.asyncio
async def test_pipeline_l3_triggers_coordinator_hook() -> None:
    """严重分歧 (余弦 < tau_arbitrate) → level=3 且调用 coordinator_hook."""
    v_a = [1.0, 0.0]
    v_b = [0.0, 1.0]  # cos=0
    embedder = FakeEmbedder({"DX-A": v_a, "DX-B": v_b})
    ops = [_op("internal", "DX-A"), _op("surgery", "DX-B")]
    routing = _routing({"internal": 0.5, "surgery": 0.5})

    called = {"n": 0, "args": None}

    async def hook(opinions, r):
        called["n"] += 1
        called["args"] = (opinions, r)
        return "仲裁稿: 综合考虑, 建议优先外科评估并完善内科检查."

    pipe = AggregationPipeline(embedder, tau_consist=0.75, tau_arbitrate=0.5)
    report, level = await pipe.aggregate(ops, routing, coordinator_hook=hook)
    assert level == 3
    assert called["n"] == 1
    assert called["args"][0] == ops
    assert report.safety_action == "arbitrated"
    assert "仲裁稿" in report.summary


@pytest.mark.asyncio
async def test_pipeline_empty_opinions() -> None:
    embedder = FakeEmbedder()
    pipe = AggregationPipeline(embedder)
    report, level = await pipe.aggregate([], _routing({"internal": 1.0}))
    assert level == 1
    assert report.dept_opinions == []
