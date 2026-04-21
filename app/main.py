"""FastAPI 入口 (论文 4.4 系统对外暴露). 阶段 4 完整接入.

四个 REST 接口:
  POST /api/v1/session                       → 创建会话, 返回 {session_id}
  POST /api/v1/consultation                  → 提交病例触发会诊, 返回 FinalReport
  GET  /api/v1/session/{sid}                 → 该会话的全部 message
  GET  /api/v1/session/{sid}/trace/{round}   → 指定轮次的 inference_meta trace

启动时通过 lifespan 一次性加载 Embedder / FaissRetriever / ModelEngine /
DepartmentRouter / DepartmentAgent / AggregationPipeline / SafetyAgent (论文要点:
模型与索引不得放在请求链路里加载, 见"几个容易踩坑的提醒").

消融开关 (R9 配置外置 + 4.5.5):
  环境变量 USE_ROUTER / USE_HYBRID_MODE / USE_SAFETY = "0" 即可关闭对应模块.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.agents.department_agent import DepartmentAgent
from app.agents.safety_agent import SafetyAgent
from app.aggregator.pipeline import AggregationPipeline
from app.coordinator.orchestrator import ConsultationOrchestrator, StorageBundle
from app.knowledge.embedder import Embedder
from app.knowledge.retriever import FaissRetriever
from app.model.inference import ModelEngine
from app.router.department_router import DepartmentRouter
from app.safety.rule_engine import SafetyChecker
from app.schemas.case import CaseSummary
from app.schemas.report import FinalReport
from app.storage.case_repo import CaseRepo
from app.storage.db import get_conn, init_schema
from app.storage.message_repo import MessageRepo
from app.storage.session_repo import SessionRepo
from app.utils.logger import get_logger, log_with

_LOG = get_logger("main")

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CFG_DIR = _PROJECT_ROOT / "config"


# ---------------- 请求/响应模型 ----------------


class SessionCreateResponse(BaseModel):
    session_id: str


class ConsultationRequest(BaseModel):
    session_id: str
    case: CaseSummary


class TraceItem(BaseModel):
    role: str
    inference_meta: Dict[str, Any] = {}
    created_at: Optional[str] = None


# ---------------- 依赖装配 ----------------


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _env_flag(name: str, default: bool = True) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip() not in {"0", "false", "False", "no", ""}


def build_default_deps() -> Dict[str, Any]:
    """构造完整运行时依赖 (生产/开发模式).

    返回字典而非单一对象, 便于测试时按需替换 (e.g. 注入 mock model 与 fake retriever).
    """
    settings = _load_yaml(_CFG_DIR / "settings.yaml")
    departments = _load_yaml(_CFG_DIR / "departments.yaml")

    # ---- 数据库 ----
    db_path = str(_PROJECT_ROOT / settings["storage"]["sqlite_path"])
    init_schema(db_path)
    conn = get_conn(db_path)
    storage = StorageBundle(
        session=SessionRepo(conn),
        case=CaseRepo(conn),
        message=MessageRepo(conn),
    )

    # ---- 模型 ----
    mcfg = settings["model"]
    model = ModelEngine(
        base_model_path=mcfg.get("base_model_path", ""),
        lora_adapter_path=mcfg.get("lora_adapter_path", ""),
        rank_bins=tuple(mcfg.get("rank_bins", (8, 16, 24, 32))),
        default_rank=int(mcfg.get("default_rank", 16)),
        mock=bool(mcfg.get("mock", True)),
    )

    # ---- 嵌入 + 检索 ----
    ecfg = settings["embedder"]
    embedder = Embedder(
        model_name_or_path=ecfg.get("model_name_or_path", "BAAI/bge-base-zh-v1.5"),
        device=ecfg.get("device", "cpu"),
        batch_size=int(ecfg.get("batch_size", 16)),
        normalize=bool(ecfg.get("normalize", True)),
    )
    retriever = FaissRetriever(embedder)
    index_path = _PROJECT_ROOT / settings["retriever"]["index_path"]
    retriever.load(index_path)
    log_with(_LOG, "info", "FAISS index loaded", path=str(index_path), n_docs=retriever.size)

    # ---- 路由 + agents ----
    dept_keys = [d["key"] for d in departments["departments"]]
    rcfg = settings["router"]
    router = DepartmentRouter(
        retriever=retriever,
        departments=dept_keys,
        tau=float(rcfg.get("tau", 0.3)),
        margin=float(rcfg.get("margin", 0.2)),
        temperature=float(rcfg.get("temperature", 1.0)),
        top_k=int(rcfg.get("top_k", 10)),
        general_dept=departments.get("general_key", "general"),
    )
    agents_map = {
        k: DepartmentAgent(dept=k, config={}, model=model, retriever=retriever)
        for k in dept_keys
    }

    # ---- 聚合 + 安全 ----
    acfg = settings["aggregator"]
    aggregator = AggregationPipeline(
        embedder=embedder,
        tau_consist=float(acfg.get("tau_consist", 0.75)),
        alpha=float(acfg.get("alpha", 1 / 3)),
        beta=float(acfg.get("beta", 1 / 3)),
        gamma=float(acfg.get("gamma", 1 / 3)),
    )
    safety_agent = SafetyAgent(
        SafetyChecker(
            rules_path=str(_CFG_DIR / "safety_rules.yaml"),
            low_risk_threshold=int(settings.get("safety", {}).get("low_risk_threshold", 2)),
        )
    )

    # ---- 协调器 ----
    orch = ConsultationOrchestrator(
        router=router,
        agents_map=agents_map,
        aggregator=aggregator,
        safety_agent=safety_agent,
        storage=storage,
        model=model,
        timeout_s=float(settings.get("timeouts", {}).get("agent_seconds", 60)),
        use_router=_env_flag("USE_ROUTER", True),
        use_hybrid=_env_flag("USE_HYBRID_MODE", True),
        use_safety=_env_flag("USE_SAFETY", True),
    )
    return {
        "orchestrator": orch,
        "storage": storage,
        "model": model,
        "embedder": embedder,
        "retriever": retriever,
        "router": router,
        "agents_map": agents_map,
    }


# ---------------- FastAPI 工厂 ----------------


def create_app(deps: Optional[Dict[str, Any]] = None) -> FastAPI:
    """允许测试通过 deps 注入 mock 组件; 不传则在 lifespan 内 build_default_deps."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if deps is not None:
            app.state.deps = deps
            log_with(_LOG, "info", "lifespan: deps injected by caller")
        else:
            log_with(_LOG, "info", "lifespan: building default deps")
            app.state.deps = build_default_deps()
        try:
            yield
        finally:
            log_with(_LOG, "info", "lifespan: shutdown")

    app = FastAPI(title="Multi-Agent Medical Consultation", version="0.4.0", lifespan=lifespan)

    # ---- 路由 ----

    @app.post("/api/v1/session", response_model=SessionCreateResponse)
    async def create_session() -> SessionCreateResponse:
        sid = app.state.deps["storage"].session.create()
        return SessionCreateResponse(session_id=sid)

    @app.post("/api/v1/consultation", response_model=FinalReport)
    async def consultation(req: ConsultationRequest) -> FinalReport:
        sess = app.state.deps["storage"].session.get(req.session_id)
        if not sess:
            raise HTTPException(status_code=404, detail="session not found")
        return await app.state.deps["orchestrator"].run(req.session_id, req.case)

    @app.get("/api/v1/sessions")
    async def list_sessions(limit: int = 50) -> List[Dict[str, Any]]:
        # 阶段 6 前端历史记录页使用. 仅读不写, 与 list_messages 同一模式 (R2).
        return app.state.deps["storage"].session.list(limit=limit)

    @app.get("/api/v1/session/{sid}")
    async def list_messages(sid: str) -> List[Dict[str, Any]]:
        sess = app.state.deps["storage"].session.get(sid)
        if not sess:
            raise HTTPException(status_code=404, detail="session not found")
        return app.state.deps["storage"].message.list(sid)

    @app.get("/api/v1/session/{sid}/trace/{round_}", response_model=List[TraceItem])
    async def trace(sid: str, round_: int) -> List[TraceItem]:
        sess = app.state.deps["storage"].session.get(sid)
        if not sess:
            raise HTTPException(status_code=404, detail="session not found")
        msgs = app.state.deps["storage"].message.list_by_round(sid, round_)
        return [
            TraceItem(
                role=m["role"],
                inference_meta=m.get("inference_meta", {}),
                created_at=m.get("created_at"),
            )
            for m in msgs
        ]

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"status": "ok"}

    return app


# 默认应用实例 (uvicorn app.main:app 时使用真实依赖装配)
app = create_app()
