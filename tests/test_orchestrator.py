"""阶段 4: 会诊协调器 + FastAPI 端到端 (mock 模型) 单测.

覆盖:
  - Orchestrator 线性流程: case 落库 / routing / agents 并行 / 三级综合 / 安全审查 / 落库
  - L3 仲裁回调 链路: aggregator → coordinator._arbitrate → model.generate(rank_hint=max)
  - inference_meta 全量落盘 (R10)
  - 消融开关 USE_ROUTER=False 时退化为全科室并行
  - FastAPI 四个 REST 接口可调通

完全使用 mock 组件, 不依赖 FAISS/BGE/真模型.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.aggregator.pipeline import AggregationPipeline  # noqa: E402
from app.coordinator.orchestrator import ConsultationOrchestrator, StorageBundle  # noqa: E402
from app.schemas.case import CaseSummary  # noqa: E402
from app.schemas.opinion import DepartmentOpinion  # noqa: E402
from app.schemas.routing import DeptCandidate, RoutingResult  # noqa: E402
from app.storage.case_repo import CaseRepo  # noqa: E402
from app.storage.db import get_conn, init_schema  # noqa: E402
from app.storage.message_repo import MessageRepo  # noqa: E402
from app.storage.session_repo import SessionRepo  # noqa: E402


# ---------------- 测试替身 ----------------


class FakeRouter:
    """按预设 RoutingResult 返回, 无需真 FAISS/embedder."""

    def __init__(self, result: RoutingResult) -> None:
        self.result = result
        self.calls = 0

    def route(self, case: CaseSummary) -> RoutingResult:
        self.calls += 1
        return self.result


class FakeAgent:
    """按 dept 输出可控诊断的伪 agent (来自 test_modes.py 同款思路)."""

    def __init__(self, dept: str, diagnosis: str = "dx", confidence: str = "high") -> None:
        self.dept = dept
        self._diagnosis = diagnosis
        self._confidence = confidence
        self.calls: List[Optional[str]] = []

    async def analyze(self, case: CaseSummary, context: Optional[str] = None) -> DepartmentOpinion:
        self.calls.append(context)
        return DepartmentOpinion(
            dept=self.dept,
            diagnosis=self._diagnosis,
            differential="dd",
            treatment="tx",
            attention="att",
            self_confidence=self._confidence,  # type: ignore[arg-type]
            inference_meta={
                "rank": 16,
                "router_weights": {"E1": 0.5, "E2": 0.5},
                "elapsed_ms": 1.0,
                "mock": True,
            },
        )


class FakeEmbedder:
    """把约定文本映射到正交单位向量, 控制 L1 余弦最小值."""

    def __init__(self, mapping: dict[str, list[float]] | None = None) -> None:
        self.mapping = mapping or {}

    def encode(self, texts: list[str]) -> np.ndarray:
        vecs = []
        for t in texts:
            if t in self.mapping:
                v = np.array(self.mapping[t], dtype=np.float32)
            else:
                h = [hash((t, i)) % 1000 / 1000.0 for i in range(4)]
                v = np.array(h, dtype=np.float32)
            n = np.linalg.norm(v)
            if n > 0:
                v = v / n
            vecs.append(v)
        return np.stack(vecs, axis=0)


class MockModel:
    """记录调用参数的 mock; rank_bins 暴露给 orchestrator._arbitrate 用."""

    def __init__(self, rank_bins: Tuple[int, ...] = (8, 16, 24, 32)) -> None:
        self.rank_bins = rank_bins
        self.calls: List[dict] = []

    def generate(self, prompt: str, rank_hint: Optional[int] = None, max_new_tokens: int = 1024):
        self.calls.append({"prompt": prompt, "rank_hint": rank_hint})
        text = (
            "诊断倾向: 仲裁后综合考虑为某诊断 (mock)\n"
            "鉴别要点: dd\n"
            "处置建议: tx\n"
            "关注事项: att\n"
            "自评置信度: medium\n"
        )
        meta = {
            "rank": rank_hint or 16,
            "router_weights": {"E1": 0.5, "E2": 0.5},
            "elapsed_ms": 1.0,
            "mock": True,
        }
        return text, meta


class NoopSafety:
    def review(self, report):
        return report


# ---------------- fixtures ----------------


@pytest.fixture()
def storage(tmp_path) -> StorageBundle:
    db = tmp_path / "test.db"
    init_schema(str(db))
    conn = get_conn(str(db))
    return StorageBundle(SessionRepo(conn), CaseRepo(conn), MessageRepo(conn))


@pytest.fixture()
def case() -> CaseSummary:
    return CaseSummary(
        case_id="c1",
        chief_complaint="右下腹剧痛 6 小时",
        symptoms="转移性右下腹痛, 伴恶心",
    )


def _routing(confs: dict[str, float], tag: str = "multi_cross") -> RoutingResult:
    cands = [DeptCandidate(dept=d, confidence=c) for d, c in confs.items()]
    cands.sort(key=lambda c: c.confidence, reverse=True)
    return RoutingResult(candidates=cands, triage_tag=tag)


# ---------------- 1. L1 通过的快速链路 ----------------


@pytest.mark.asyncio
async def test_orchestrator_l1_pass_persists_messages(storage, case) -> None:
    routing = _routing({"internal": 0.4, "surgery": 0.6}, tag="multi_cross")
    router = FakeRouter(routing)
    agents_map = {
        "internal": FakeAgent("internal", diagnosis="急性阑尾炎"),
        "surgery": FakeAgent("surgery", diagnosis="急性阑尾炎"),
    }
    aggregator = AggregationPipeline(FakeEmbedder(), tau_consist=0.75)
    model = MockModel()
    orch = ConsultationOrchestrator(
        router=router,
        agents_map=agents_map,
        aggregator=aggregator,
        safety_agent=NoopSafety(),
        storage=storage,
        model=model,
    )
    sid = storage.session.create()
    report = await orch.run(sid, case)

    assert report.aggregation_level == 1
    # L1 不应触发仲裁
    assert model.calls == []
    # 路由 / 两条意见 / 一份报告 都已落库
    msgs = storage.message.list(sid)
    roles = [m["role"] for m in msgs]
    assert roles.count("routing") == 1
    assert roles.count("opinion") == 2
    assert roles.count("report") == 1
    # R10: opinion 的 inference_meta 全量保存 (rank/router_weights/elapsed_ms)
    op_msgs = [m for m in msgs if m["role"] == "opinion"]
    for m in op_msgs:
        meta = m["inference_meta"]
        assert "rank" in meta and "router_weights" in meta and "elapsed_ms" in meta
    # report 的 meta 含 aggregation_level / mode
    rep_meta = [m["inference_meta"] for m in msgs if m["role"] == "report"][0]
    assert rep_meta["aggregation_level"] == 1
    assert rep_meta["mode"] in {"parallel", "hybrid", "serial"}


# ---------------- 2. L3 触发: 协调器 _arbitrate 用 max(rank_bins) ----------------


@pytest.mark.asyncio
async def test_orchestrator_l3_invokes_arbitration_with_max_rank(storage, case) -> None:
    """两科室诊断完全正交 → 余弦=0 → L3 → _arbitrate 调 model.generate(rank_hint=32)."""
    routing = _routing({"internal": 0.5, "surgery": 0.5}, tag="multi_cross")
    router = FakeRouter(routing)
    agents_map = {
        "internal": FakeAgent("internal", diagnosis="DX-A"),
        "surgery": FakeAgent("surgery", diagnosis="DX-B"),
    }
    embedder = FakeEmbedder({"DX-A": [1.0, 0.0], "DX-B": [0.0, 1.0]})
    aggregator = AggregationPipeline(embedder, tau_consist=0.75, tau_arbitrate=0.5)
    model = MockModel(rank_bins=(8, 16, 24, 32))
    orch = ConsultationOrchestrator(
        router=router,
        agents_map=agents_map,
        aggregator=aggregator,
        safety_agent=NoopSafety(),
        storage=storage,
        model=model,
    )
    sid = storage.session.create()
    report = await orch.run(sid, case)

    assert report.aggregation_level == 3
    # 关键断言: 协调器**显式**以 max(rank_bins)=32 调模型 (R5)
    assert len(model.calls) == 1
    assert model.calls[0]["rank_hint"] == 32
    # report 落库的 meta 反映 L3
    rep_meta = [m["inference_meta"] for m in storage.message.list(sid) if m["role"] == "report"][0]
    assert rep_meta["aggregation_level"] == 3
    assert rep_meta["safety_action"] == "arbitrated"


# ---------------- 3. 消融: USE_ROUTER=False ----------------


@pytest.mark.asyncio
async def test_orchestrator_ablation_no_router(storage, case) -> None:
    """关闭 router 后, 不调用 router.route, 全科室都被并发激活."""
    routing_ignored = _routing({"internal": 1.0}, tag="single_clear")
    router = FakeRouter(routing_ignored)
    agents_map = {
        "internal": FakeAgent("internal", diagnosis="同一诊断"),
        "surgery": FakeAgent("surgery", diagnosis="同一诊断"),
        "general": FakeAgent("general", diagnosis="同一诊断"),
    }
    aggregator = AggregationPipeline(FakeEmbedder(), tau_consist=0.75)
    orch = ConsultationOrchestrator(
        router=router,
        agents_map=agents_map,
        aggregator=aggregator,
        safety_agent=NoopSafety(),
        storage=storage,
        model=MockModel(),
        use_router=False,
        default_mode="parallel",
    )
    sid = storage.session.create()
    await orch.run(sid, case)

    assert router.calls == 0  # 未调用 router
    op_msgs = [m for m in storage.message.list(sid) if m["role"] == "opinion"]
    # 三个科室都被激活
    assert {m["payload"]["dept"] for m in op_msgs} == {"internal", "surgery", "general"}


# ---------------- 4. FastAPI 端到端 ----------------


def _build_app_with_mocks(storage: StorageBundle):
    from app.main import create_app

    routing = _routing({"internal": 0.5, "surgery": 0.5}, tag="multi_cross")
    router = FakeRouter(routing)
    agents_map = {
        "internal": FakeAgent("internal", diagnosis="DX-A"),
        "surgery": FakeAgent("surgery", diagnosis="DX-B"),
    }
    embedder = FakeEmbedder({"DX-A": [1.0, 0.0], "DX-B": [0.0, 1.0]})
    aggregator = AggregationPipeline(embedder, tau_consist=0.75, tau_arbitrate=0.5)
    model = MockModel(rank_bins=(8, 16, 24, 32))
    orch = ConsultationOrchestrator(
        router=router,
        agents_map=agents_map,
        aggregator=aggregator,
        safety_agent=NoopSafety(),
        storage=storage,
        model=model,
    )
    deps = {"orchestrator": orch, "storage": storage, "model": model}
    return create_app(deps=deps), model


def test_fastapi_endpoints_end_to_end(storage) -> None:
    from fastapi.testclient import TestClient

    app, model = _build_app_with_mocks(storage)
    with TestClient(app) as client:
        # health
        assert client.get("/healthz").json() == {"status": "ok"}

        # 1) create session
        resp = client.post("/api/v1/session")
        assert resp.status_code == 200
        sid = resp.json()["session_id"]
        assert sid

        # 2) consultation: 触发 L3 仲裁
        case_payload = {
            "session_id": sid,
            "case": {
                "case_id": "c-e2e",
                "chief_complaint": "右下腹痛 6 小时",
                "symptoms": "转移性右下腹痛",
                "medical_history": "",
                "exam_results": "",
            },
        }
        resp = client.post("/api/v1/consultation", json=case_payload)
        assert resp.status_code == 200, resp.text
        report = resp.json()
        assert report["aggregation_level"] == 3
        assert report["safety_action"] == "arbitrated"
        # R5 显式 max rank_hint
        assert model.calls and model.calls[0]["rank_hint"] == 32

        # 3) list session messages
        resp = client.get(f"/api/v1/session/{sid}")
        assert resp.status_code == 200
        msgs = resp.json()
        assert {m["role"] for m in msgs} >= {"routing", "opinion", "report"}

        # 4) trace by round
        resp = client.get(f"/api/v1/session/{sid}/trace/1")
        assert resp.status_code == 200
        traces = resp.json()
        assert len(traces) >= 4
        # opinion 行的 inference_meta 应有 rank
        op_traces = [t for t in traces if t["role"] == "opinion"]
        assert all("rank" in t["inference_meta"] for t in op_traces)

        # 5) 不存在的 session 返回 404
        assert client.get("/api/v1/session/nonexistent").status_code == 404
        assert client.get("/api/v1/session/nonexistent/trace/1").status_code == 404
        bad = client.post(
            "/api/v1/consultation",
            json={**case_payload, "session_id": "nonexistent"},
        )
        assert bad.status_code == 404
