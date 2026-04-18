"""会诊状态机 (论文 4.3.1).

六状态有限自动机:

    Idle → Routing → Consulting → Aggregating → Done
                                              ↘ Error
    任意非终态都可在异常时迁向 Error.

设计要点:
- 仅 ``ConsultationOrchestrator`` 持有 ``StateMachine`` 实例, 由其在 ``run`` 中显式
  推进状态; 模块间不共享.
- ``transition`` 通过白名单校验合法性, 非法迁移抛 ``IllegalTransition``, 防止
  "Aggregating → Routing" 等回退导致脏数据 (R2 状态一致性).
- 通过 ``add_listener`` 注入回调, 协调器借此把每次状态切换写入 ``message`` 表
  (role="state"), 满足 R10 全量可追溯.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


class State(str, Enum):
    """六状态. 字符串化便于直接 JSON 序列化落库."""

    IDLE = "idle"
    ROUTING = "routing"
    CONSULTING = "consulting"
    AGGREGATING = "aggregating"
    DONE = "done"
    ERROR = "error"


class IllegalTransition(RuntimeError):
    """非法状态迁移. 例如 Done → Routing 或 Aggregating → Idle."""


# 合法迁移白名单. 任意非终态均可迁向 Error (统一在 transition 内处理).
_ALLOWED: Dict[State, Set[State]] = {
    State.IDLE: {State.ROUTING},
    State.ROUTING: {State.CONSULTING},
    State.CONSULTING: {State.AGGREGATING},
    State.AGGREGATING: {State.DONE},
    State.DONE: set(),
    State.ERROR: set(),
}

Listener = Callable[[State, State, Dict[str, Any]], None]


class StateMachine:
    def __init__(
        self,
        initial: State = State.IDLE,
        listeners: Optional[List[Listener]] = None,
    ) -> None:
        self._state: State = initial
        self._history: List[Tuple[State, State, Dict[str, Any]]] = []
        self._listeners: List[Listener] = list(listeners or [])

    # --------- 查询 ---------

    @property
    def state(self) -> State:
        return self._state

    @property
    def history(self) -> List[Tuple[State, State, Dict[str, Any]]]:
        return list(self._history)

    @property
    def is_terminal(self) -> bool:
        return self._state in (State.DONE, State.ERROR)

    def can_transition(self, target: State) -> bool:
        if target is State.ERROR:
            # Error 是兜底终态, 任意非终态都可进入
            return not self.is_terminal
        return target in _ALLOWED[self._state]

    # --------- 监听器 ---------

    def add_listener(self, listener: Listener) -> None:
        self._listeners.append(listener)

    # --------- 迁移 ---------

    def transition(self, target: State, meta: Optional[Dict[str, Any]] = None) -> State:
        meta = dict(meta or {})
        if not self.can_transition(target):
            raise IllegalTransition(
                f"illegal transition: {self._state.value} -> {target.value}"
            )
        prev = self._state
        self._state = target
        self._history.append((prev, target, meta))
        for cb in self._listeners:
            # 回调异常不得影响主流程 (落库失败不应导致状态机崩溃)
            try:
                cb(prev, target, meta)
            except Exception:  # noqa: BLE001
                pass
        return target

    def fail(self, reason: str, **extra: Any) -> None:
        """统一的错误兜底入口. 已在终态时为幂等空操作."""
        if self.is_terminal:
            return
        payload: Dict[str, Any] = {"reason": reason}
        payload.update(extra)
        self.transition(State.ERROR, payload)
