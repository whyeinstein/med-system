"""抽象基类: prompt 装配 + 模型调用 + 输出解析.

阶段 2: 将公共流水 (读模板 / 检索 / 组 prompt / 异步调模型 / 解析) 抽到本基类,
子类 (DepartmentAgent) 只需实现 `analyze()` 的业务编排.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from app.knowledge.retriever import FaissRetriever, Hit
from app.model.inference import ModelEngine
from app.schemas.case import CaseSummary
from app.schemas.opinion import DepartmentOpinion
from app.utils.logger import get_logger, log_with
from app.utils.parser import parse_opinion_text

_LOG = get_logger("agents.base")

# 项目根目录 (本文件 -> app/agents -> app -> 根)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PROMPT_DIR = _PROJECT_ROOT / "config" / "prompts"


class BaseAgent(ABC):
    """所有科室 / 安全 agent 的基类."""

    def __init__(
        self,
        dept: str,
        config: dict,
        model: ModelEngine,
        retriever: Optional[FaissRetriever],
        prompt_dir: Optional[Path] = None,
    ) -> None:
        self.dept = dept
        self.config = config or {}
        self.model = model
        self.retriever = retriever
        self._prompt_dir = Path(prompt_dir) if prompt_dir else _DEFAULT_PROMPT_DIR
        self._dept_cfg = self._load_dept_config()
        self._base_template = self._load_base_template()

    # ---------------- 配置与模板 ----------------

    def _load_dept_config(self) -> dict:
        """读取 config/prompts/<dept>.yaml, 不存在则回退空字典."""
        path = self._prompt_dir / f"{self.dept}.yaml"
        if not path.exists():
            log_with(_LOG, "warning", "dept prompt yaml missing", dept=self.dept, path=str(path))
            return {}
        with path.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}

    def _load_base_template(self) -> str:
        path = self._prompt_dir / "base_template.txt"
        return path.read_text(encoding="utf-8")

    @property
    def display_name(self) -> str:
        return self._dept_cfg.get("display", self.dept)

    # ---------------- 检索 + 两步过滤 ----------------

    def _retrieve_knowledge(self, case: CaseSummary, top_k: int = 5) -> List[Hit]:
        """论文 4.3.3 两步过滤:
          1) 相似度差值去尾: 仅保留 score >= top1_score - drop_margin 的命中.
          2) 科室标签一致性: 仅保留 dept == self.dept; 若全被过滤, 回退为相似度最高的 1 条.
        """
        if self.retriever is None:
            return []
        query = f"{case.chief_complaint} {self.display_name}".strip()
        try:
            hits = self.retriever.search(query, top_k=top_k)
        except RuntimeError:
            # 索引未初始化 (测试环境). 返回空, 不阻塞流程.
            return []
        if not hits:
            return []
        drop_margin = 0.1
        top_score = hits[0].score
        filtered = [h for h in hits if h.score >= top_score - drop_margin]
        same_dept = [h for h in filtered if h.dept == self.dept]
        if same_dept:
            return same_dept
        return filtered[:1]

    @staticmethod
    def _format_knowledge(hits: List[Hit]) -> str:
        if not hits:
            return "(无可用参考知识)"
        lines = []
        for i, h in enumerate(hits, 1):
            snippet = h.text.strip().replace("\n", " ")
            lines.append(f"[{i}] ({h.dept}, sim={h.score:.3f}) {snippet}")
        return "\n".join(lines)

    # ---------------- prompt 装配 ----------------

    def _build_prompt(
        self,
        case: CaseSummary,
        retrieved: List[Hit],
        context: Optional[str] = None,
    ) -> str:
        """按 base_template.txt 的占位符填充.

        R4: 严禁注入"激活第 X 号专家 / 使用科室 Y 的路由"类指令 —— 两层专家为软对应.
        """
        prior_block = ""
        if context:
            prior_block = f"## 前序会诊意见 (仅供参考, 不要简单复述)\n{context.strip()}\n"
        values = {
            "dept_display": self.display_name,
            "role_detail": (self._dept_cfg.get("role_detail") or "").strip(),
            "reasoning_focus": (self._dept_cfg.get("reasoning_focus") or "").strip(),
            "retrieved_knowledge": self._format_knowledge(retrieved),
            "chief_complaint": case.chief_complaint or "(未提供)",
            "symptoms": case.symptoms or "(未提供)",
            "medical_history": case.medical_history or "(无)",
            "exam_results": case.exam_results or "(无)",
            "prior_context_block": prior_block,
        }
        try:
            return self._base_template.format(**values)
        except KeyError as e:  # pragma: no cover
            raise RuntimeError(f"base_template 缺少占位符 {e}") from e

    # ---------------- 模型调用 ----------------

    async def _generate(
        self,
        prompt: str,
        rank_hint: Optional[int] = None,
    ) -> Tuple[str, dict]:
        """R8: 同步推理必须 asyncio.to_thread 包装, 不得直接在事件循环里阻塞."""
        return await asyncio.to_thread(self.model.generate, prompt, rank_hint)

    # ---------------- 解析 + 组装 ----------------

    def _compose_opinion(
        self,
        text: str,
        meta: dict,
        retrieved: List[Hit],
    ) -> DepartmentOpinion:
        fields = parse_opinion_text(text)
        inference_meta = {
            "rank": meta.get("rank"),
            "router_weights": meta.get("router_weights"),
            "elapsed_ms": meta.get("elapsed_ms"),
            "mock": meta.get("mock"),
            "retrieval": [
                {"dept": h.dept, "score": round(h.score, 4), "source": h.source_path}
                for h in retrieved
            ],
            "raw_text": text,
        }
        return DepartmentOpinion(
            dept=self.dept,
            diagnosis=fields.get("diagnosis", ""),
            differential=fields.get("differential", ""),
            treatment=fields.get("treatment", ""),
            attention=fields.get("attention", ""),
            self_confidence=fields.get("self_confidence", "medium"),  # type: ignore[arg-type]
            inference_meta=inference_meta,
        )

    # ---------------- 子类必须实现 ----------------

    @abstractmethod
    async def analyze(
        self,
        case: CaseSummary,
        context: Optional[str] = None,
    ) -> DepartmentOpinion:
        raise NotImplementedError
