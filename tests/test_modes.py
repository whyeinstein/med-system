"""阶段 2: 三种会诊模式流程单测.

使用计数型 FakeAgent, 断言:
  - parallel 并发一次调用所有 agent
  - serial 顺序调用, 且后续 agent 能拿到前序 context
  - hybrid: 核心组弱意见时激活辅助组, 强意见时跳过
  - mode_selector: 不同 triage_tag 返回不同模式
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import List, Optional

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.modes.hybrid import run_hybrid  # noqa: E402
from app.modes.mode_selector import select_mode  # noqa: E402
from app.modes.parallel import run_parallel  # noqa: E402
from app.modes.serial import run_serial  # noqa: E402
from app.schemas.case import CaseSummary  # noqa: E402
from app.schemas.opinion import DepartmentOpinion  # noqa: E402
from app.schemas.routing import DeptCandidate, RoutingResult  # noqa: E402


class FakeAgent:
    """计数 + 记录 context + 可配置耗时/置信度的伪 agent."""

    def __init__(
        self,
        dept: str,
        confidence: str = "high",
        diagnosis: str = "dx",
        delay: float = 0.0,
        raise_timeout: bool = False,
    ) -> None:
        self.dept = dept
        self._confidence = confidence
        self._diagnosis = diagnosis
        self._delay = delay
        self._raise_timeout = raise_timeout
        self.calls: List[Optional[str]] = []

    async def analyze(self, case: CaseSummary, context: Optional[str] = None) -> DepartmentOpinion:
        self.calls.append(context)
        if self._raise_timeout:
            await asyncio.sleep(10)  # 配合 wait_for 超时
        if self._delay:
            await asyncio.sleep(self._delay)
        return DepartmentOpinion(
            dept=self.dept,
            diagnosis=self._diagnosis,
            differential="dd",
            treatment="tx",
            attention="att",
            self_confidence=self._confidence,  # type: ignore[arg-type]
            inference_meta={"rank": 16, "router_weights": {}, "elapsed_ms": 1.0},
        )


@pytest.fixture
def case() -> CaseSummary:
    return CaseSummary(case_id="t", chief_complaint="cc", symptoms="sym")


# ---------------- mode_selector ----------------


def _routing(tag: str, confs: list[float]) -> RoutingResult:
    cands = [DeptCandidate(dept=f"d{i}", confidence=c) for i, c in enumerate(confs)]
    return RoutingResult(candidates=cands, triage_tag=tag)  # type: ignore[arg-type]


def test_select_mode_single_clear() -> None:
    assert select_mode(_routing("single_clear", [0.8, 0.1, 0.05, 0.05])) == "serial"


def test_select_mode_ambiguous() -> None:
    assert select_mode(_routing("ambiguous", [0.25, 0.25, 0.25, 0.25])) == "parallel"


def test_select_mode_multi_cross_hybrid() -> None:
    # 3 个科室超过核心阈值, 总数 4 → hybrid
    assert select_mode(_routing("multi_cross", [0.35, 0.3, 0.25, 0.1])) == "hybrid"


def test_select_mode_multi_cross_parallel_when_no_aux() -> None:
    # 只 2 个科室都进核心, 没有辅助组 → parallel
    assert select_mode(_routing("multi_cross", [0.55, 0.45])) == "parallel"


# ---------------- parallel ----------------


@pytest.mark.asyncio
async def test_parallel_calls_all(case: CaseSummary) -> None:
    agents = [FakeAgent("internal"), FakeAgent("surgery"), FakeAgent("pediatrics")]
    ops = await run_parallel(agents, case, timeout_s=5)
    assert len(ops) == 3
    assert {o.dept for o in ops} == {"internal", "surgery", "pediatrics"}
    # context 应为空 (并行模式不注入前序意见)
    for a in agents:
        assert a.calls == [None]


@pytest.mark.asyncio
async def test_parallel_timeout_filters_agent(case: CaseSummary) -> None:
    agents = [FakeAgent("internal"), FakeAgent("surgery", raise_timeout=True)]
    ops = await run_parallel(agents, case, timeout_s=0.1)
    assert len(ops) == 1
    assert ops[0].dept == "internal"


# ---------------- serial ----------------


@pytest.mark.asyncio
async def test_serial_passes_context(case: CaseSummary) -> None:
    a, b, c = FakeAgent("internal"), FakeAgent("surgery"), FakeAgent("pediatrics")
    ops = await run_serial([a, b, c], case, timeout_s=5)
    assert [o.dept for o in ops] == ["internal", "surgery", "pediatrics"]
    # 第一个 agent 无 context, 后续 agent 能看到前序 dept 标签
    assert a.calls == [None]
    assert b.calls and "[internal]" in b.calls[0]
    assert c.calls and "[internal]" in c.calls[0] and "[surgery]" in c.calls[0]


# ---------------- hybrid ----------------


@pytest.mark.asyncio
async def test_hybrid_skips_aux_when_core_strong(case: CaseSummary) -> None:
    core = [FakeAgent("internal", confidence="high"), FakeAgent("surgery", confidence="high")]
    aux = [FakeAgent("general"), FakeAgent("pediatrics")]
    ops = await run_hybrid(core, aux, case, timeout_s=5)
    assert {o.dept for o in ops} == {"internal", "surgery"}
    # 辅助组未被触发
    assert all(a.calls == [] for a in aux)


@pytest.mark.asyncio
async def test_hybrid_activates_aux_when_core_weak(case: CaseSummary) -> None:
    core = [FakeAgent("internal", confidence="low"), FakeAgent("surgery", confidence="low")]
    aux = [FakeAgent("general"), FakeAgent("pediatrics")]
    ops = await run_hybrid(core, aux, case, timeout_s=5)
    assert {o.dept for o in ops} == {"internal", "surgery", "general", "pediatrics"}
    assert all(a.calls == [None] for a in aux)
