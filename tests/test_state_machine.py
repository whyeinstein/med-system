"""阶段 5 单测: 状态机 + 任务队列三级容错 + 协调器状态机驱动闭环.

覆盖:
  1. StateMachine 合法迁移 / 非法迁移 / 终态拒绝再迁移 / Error 兜底
  2. listener 回调按序收到 (prev, target, meta)
  3. TaskQueue L1 重试: 前 N 次失败, 第 N+1 次成功 → status=success, attempts 正确
  4. TaskQueue L2 缺席: 重试耗尽 → status=absent, 不阻塞其他任务
  5. TaskQueue L3 全局降级: absent 比例越阈值 → degraded=True, 触发 on_degrade 回调
  6. Orchestrator 状态机闭环: state 消息按 Idle→Routing→Consulting→Aggregating→Done 顺序落库
  7. Orchestrator 全局降级 (所有 agent 一直超时) → 进入 Error 状态, 落 role=error
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.aggregator.pipeline import AggregationPipeline  # noqa: E402
from app.coordinator.orchestrator import ConsultationOrchestrator, StorageBundle  # noqa: E402
from app.coordinator.state_machine import (  # noqa: E402
    IllegalTransition,
    State,
    StateMachine,
)
from app.coordinator.task_queue import QueueResult, TaskQueue  # noqa: E402
from app.schemas.case import CaseSummary  # noqa: E402
from app.schemas.opinion import DepartmentOpinion  # noqa: E402
from app.schemas.routing import DeptCandidate, RoutingResult  # noqa: E402
from app.storage.case_repo import CaseRepo  # noqa: E402
from app.storage.db import get_conn, init_schema  # noqa: E402
from app.storage.message_repo import MessageRepo  # noqa: E402
from app.storage.session_repo import SessionRepo  # noqa: E402


# =====================================================================
# 1. StateMachine
# =====================================================================


def test_state_machine_happy_path_sequence() -> None:
    sm = StateMachine()
    events: List[Tuple[State, State, dict]] = []
    sm.add_listener(lambda p, t, m: events.append((p, t, m)))

    assert sm.state is State.IDLE
    sm.transition(State.ROUTING, {"case_id": "c1"})
    sm.transition(State.CONSULTING, {"mode": "parallel"})
    sm.transition(State.AGGREGATING, {})
    sm.transition(State.DONE, {"safety_action": "pass"})

    assert sm.state is State.DONE
    assert sm.is_terminal
    transitions = [(p, t) for p, t, _ in events]
    assert transitions == [
        (State.IDLE, State.ROUTING),
        (State.ROUTING, State.CONSULTING),
        (State.CONSULTING, State.AGGREGATING),
        (State.AGGREGATING, State.DONE),
    ]
    assert events[0][2] == {"case_id": "c1"}


def test_state_machine_rejects_illegal_transition() -> None:
    sm = StateMachine()
    # Idle 不能直接到 Aggregating
    with pytest.raises(IllegalTransition):
        sm.transition(State.AGGREGATING)
    # 进入 Routing 后不能回到 Idle
    sm.transition(State.ROUTING)
    with pytest.raises(IllegalTransition):
        sm.transition(State.IDLE)


def test_state_machine_terminal_blocks_further_transitions() -> None:
    sm = StateMachine()
    sm.transition(State.ROUTING)
    sm.fail("boom")
    assert sm.state is State.ERROR
    assert sm.is_terminal
    # 进入 Error 后, 任何 transition 都非法 (含再次 fail 静默幂等)
    with pytest.raises(IllegalTransition):
        sm.transition(State.CONSULTING)
    sm.fail("again")  # 幂等空操作, 不抛
    assert sm.state is State.ERROR


def test_state_machine_error_can_be_entered_from_any_non_terminal() -> None:
    for entry in (State.ROUTING, State.CONSULTING, State.AGGREGATING):
        sm = StateMachine()
        sm.transition(State.ROUTING)
        if entry is State.CONSULTING:
            sm.transition(State.CONSULTING)
        elif entry is State.AGGREGATING:
            sm.transition(State.CONSULTING)
            sm.transition(State.AGGREGATING)
        sm.fail("x")
        assert sm.state is State.ERROR


# =====================================================================
# 2. TaskQueue 三级容错
# =====================================================================


@pytest.mark.asyncio
async def test_task_queue_l1_retry_recovers() -> None:
    """前 1 次抛异常, 第 2 次成功; max_retries=1 应能恢复."""
    counter = {"n": 0}

    async def flaky():
        counter["n"] += 1
        if counter["n"] == 1:
            raise RuntimeError("transient")
        return "ok"

    q = TaskQueue(timeout_s=1.0, max_retries=1, degrade_ratio=1.0)
    res = await q.run([("a", flaky)])
    assert res.results == ["ok"]
    assert res.absent == []
    assert res.records[0].status == "success"
    assert res.records[0].attempts == 2


@pytest.mark.asyncio
async def test_task_queue_l2_absent_does_not_block_others() -> None:
    """一个任务持续超时被标 absent, 其他任务正常完成."""

    async def hangs():
        await asyncio.sleep(10.0)
        return "never"

    async def quick():
        return "fast"

    q = TaskQueue(timeout_s=0.05, max_retries=1, degrade_ratio=1.0)
    res = await q.run([("slow", hangs), ("fast", quick)])
    assert res.results == ["fast"]
    assert res.absent == ["slow"]
    slow_rec = next(r for r in res.records if r.label == "slow")
    assert slow_rec.status == "absent"
    assert slow_rec.attempts == 2  # 首次 + 1 次重试
    assert "timeout" in (slow_rec.last_error or "")
    assert res.degraded is False  # 50% 未达默认 0.5? 注: 0.5>=0.5 会触发, 这里阈值=1.0


@pytest.mark.asyncio
async def test_task_queue_l3_global_degrade_invokes_callback() -> None:
    """absent 比例 >= degrade_ratio 时触发降级回调."""
    captured: List[QueueResult] = []

    async def fail_now():
        raise RuntimeError("nope")

    async def quick():
        return "ok"

    q = TaskQueue(
        timeout_s=0.5,
        max_retries=0,
        degrade_ratio=0.5,
        on_degrade=lambda r: captured.append(r),
    )
    res = await q.run([("a", fail_now), ("b", fail_now), ("c", quick)])
    # 2/3 absent >= 0.5 → degraded
    assert res.degraded is True
    assert sorted(res.absent) == ["a", "b"]
    assert res.results == ["ok"]
    assert len(captured) == 1
    assert captured[0].degraded is True
    assert "absent" in (captured[0].degrade_reason or "")


@pytest.mark.asyncio
async def test_task_queue_empty_returns_empty_result() -> None:
    q = TaskQueue()
    res = await q.run([])
    assert res.total == 0
    assert res.results == []
    assert res.degraded is False


# =====================================================================
# 3. Orchestrator 状态机闭环
# =====================================================================


class _FakeRouter:
    def __init__(self, result: RoutingResult) -> None:
        self.result = result

    def route(self, case: CaseSummary) -> RoutingResult:
        return self.result


class _FakeAgent:
    def __init__(self, dept: str, diagnosis: str = "dx") -> None:
        self.dept = dept
        self._dx = diagnosis

    async def analyze(self, case: CaseSummary, context: Optional[str] = None) -> DepartmentOpinion:
        return DepartmentOpinion(
            dept=self.dept,
            diagnosis=self._dx,
            differential="dd",
            treatment="tx",
            attention="att",
            self_confidence="high",
            inference_meta={"rank": 16, "router_weights": {}, "elapsed_ms": 0.1, "mock": True},
        )


class _AlwaysTimeoutAgent:
    def __init__(self, dept: str) -> None:
        self.dept = dept

    async def analyze(self, case: CaseSummary, context: Optional[str] = None):
        await asyncio.sleep(10.0)
        raise RuntimeError("unreachable")


class _NoopSafety:
    def review(self, report):
        return report


class _FakeEmbedder:
    def encode(self, texts):
        # 同诊断 → 余弦=1, 走 L1
        v = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        return np.stack([v for _ in texts], axis=0)


class _MockModel:
    def __init__(self) -> None:
        self.rank_bins = (8, 16, 24, 32)
        self.calls: List[dict] = []

    def generate(self, prompt: str, rank_hint: Optional[int] = None, max_new_tokens: int = 1024):
        self.calls.append({"prompt": prompt, "rank_hint": rank_hint})
        return ("诊断倾向: x\n鉴别要点: x\n处置建议: x\n关注事项: x\n自评置信度: medium\n",
                {"rank": rank_hint or 16, "router_weights": {}, "elapsed_ms": 0.1, "mock": True})


@pytest.fixture()
def storage(tmp_path) -> StorageBundle:
    db = tmp_path / "test.db"
    init_schema(str(db))
    conn = get_conn(str(db))
    return StorageBundle(SessionRepo(conn), CaseRepo(conn), MessageRepo(conn))


@pytest.fixture()
def case() -> CaseSummary:
    return CaseSummary(case_id="c1", chief_complaint="x", symptoms="y")


def _routing(confs, tag="multi_cross") -> RoutingResult:
    cands = [DeptCandidate(dept=d, confidence=c) for d, c in confs.items()]
    cands.sort(key=lambda c: c.confidence, reverse=True)
    return RoutingResult(candidates=cands, triage_tag=tag)


@pytest.mark.asyncio
async def test_orchestrator_drives_state_machine_and_persists_state_messages(
    storage, case
) -> None:
    routing = _routing({"internal": 0.5, "surgery": 0.5}, tag="multi_cross")
    agents_map = {
        "internal": _FakeAgent("internal", diagnosis="同诊断"),
        "surgery": _FakeAgent("surgery", diagnosis="同诊断"),
    }
    aggregator = AggregationPipeline(_FakeEmbedder(), tau_consist=0.75)
    orch = ConsultationOrchestrator(
        router=_FakeRouter(routing),
        agents_map=agents_map,
        aggregator=aggregator,
        safety_agent=_NoopSafety(),
        storage=storage,
        model=_MockModel(),
    )
    sid = storage.session.create()
    report = await orch.run(sid, case)
    assert report.aggregation_level == 1

    # state 消息按 Idle→Routing→Consulting→Aggregating→Done 顺序写入
    state_msgs = [m for m in storage.message.list(sid) if m["role"] == "state"]
    transitions = [(m["payload"]["from"], m["payload"]["to"]) for m in state_msgs]
    assert transitions == [
        ("idle", "routing"),
        ("routing", "consulting"),
        ("consulting", "aggregating"),
        ("aggregating", "done"),
    ]
    # 不应出现 error
    assert not any(m["role"] == "error" for m in storage.message.list(sid))


@pytest.mark.asyncio
async def test_orchestrator_global_degrade_transitions_to_error(storage, case) -> None:
    """两个 agent 都持续超时 → TaskQueue 全部 absent → 全局降级 → 进入 Error 状态."""
    routing = _routing({"internal": 0.5, "surgery": 0.5}, tag="multi_cross")
    agents_map = {
        "internal": _AlwaysTimeoutAgent("internal"),
        "surgery": _AlwaysTimeoutAgent("surgery"),
    }
    aggregator = AggregationPipeline(_FakeEmbedder(), tau_consist=0.75)
    # 极短超时 + 0 重试触发 absent
    tq = TaskQueue(timeout_s=0.05, max_retries=0, degrade_ratio=0.5)
    orch = ConsultationOrchestrator(
        router=_FakeRouter(routing),
        agents_map=agents_map,
        aggregator=aggregator,
        safety_agent=_NoopSafety(),
        storage=storage,
        model=_MockModel(),
        task_queue=tq,
    )
    sid = storage.session.create()
    with pytest.raises(RuntimeError, match="global degrade"):
        await orch.run(sid, case)

    msgs = storage.message.list(sid)
    state_msgs = [m for m in msgs if m["role"] == "state"]
    # 最后一次状态切换必须是迁入 error
    assert state_msgs[-1]["payload"]["to"] == "error"
    assert state_msgs[-1]["payload"]["reason"] == "global_degrade_no_opinions"
    # 同时落了一条 role="error" 便于排障
    err_msgs = [m for m in msgs if m["role"] == "error"]
    assert len(err_msgs) == 1
    assert err_msgs[0]["inference_meta"]["final_state"] == "error"
    # opinion 一条都不应该有
    assert not any(m["role"] == "opinion" for m in msgs)
