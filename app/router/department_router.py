"""路由调度器. 严格遵循论文 4.3.2:
1) 语义检索 top_k
2) 按 dept 分组取相似度 **最大值** (非均值, 避免噪声片段累积)
3) softmax 归一化为 confidence (在全部已注册科室上做归一)
4) **候选筛选**: Top-K 截断 + tau_keep 阈值过滤, 仅保留高置信子集
   (避免把近 0 的科室也算成候选, 否则 multi_cross 会成为常态, 路由形同虚设)
5) triage_tag (基于筛选后的候选集判断):
   - top1 - top2 > margin → single_clear
   - top1 < tau          → ambiguous (fallback)
   - 其他                → multi_cross
"""
from __future__ import annotations

import math
from typing import Dict, List

from app.knowledge.retriever import FaissRetriever, Hit
from app.schemas.case import CaseSummary
from app.schemas.routing import DeptCandidate, RoutingResult
from app.router.fallback import apply_fallback


class DepartmentRouter:
    def __init__(
        self,
        retriever: FaissRetriever,
        departments: List[str],
        tau: float = 0.3,
        margin: float = 0.2,
        temperature: float = 1.0,
        top_k: int = 10,
        top_k_keep: int = 3,
        tau_keep: float = 0.10,
        general_dept: str = "general",
    ) -> None:
        if not departments:
            raise ValueError("departments 不能为空")
        self.retriever = retriever
        self.departments = list(departments)
        self.tau = tau
        self.margin = margin
        self.temperature = max(temperature, 1e-6)
        self.top_k = top_k
        self.top_k_keep = max(1, int(top_k_keep))
        self.tau_keep = float(tau_keep)
        self.general_dept = general_dept

    def route(self, case: CaseSummary) -> RoutingResult:
        query = f"{case.chief_complaint} {case.symptoms}".strip()
        hits = self.retriever.search(query, top_k=self.top_k)

        raw_scores = self._group_max(hits)
        candidates = self._softmax(raw_scores)
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        # 候选筛选: Top-K + 阈值 (至少保留 1 个, 否则 fallback 兜底)
        candidates = self._filter_candidates(candidates)

        triage_tag = self._classify(candidates)

        result = RoutingResult(
            candidates=candidates,
            triage_tag=triage_tag,
            fallback_triggered=False,
            retrieval_hits=[_hit_to_dict(h) for h in hits],
        )
        if triage_tag == "ambiguous":
            result = apply_fallback(result, general_dept=self.general_dept)
        return result

    # ---------------- internal ----------------

    def _group_max(self, hits: List[Hit]) -> Dict[str, float]:
        """按 dept 取命中中的最大相似度; 未命中科室给 0 (参与 softmax 保留在候选集合)."""
        scores: Dict[str, float] = {d: 0.0 for d in self.departments}
        for h in hits:
            if h.dept in scores:
                if h.score > scores[h.dept]:
                    scores[h.dept] = h.score
            # 未登记科室的命中忽略, 避免污染候选集
        return scores

    def _softmax(self, raw: Dict[str, float]) -> List[DeptCandidate]:
        depts = list(raw.keys())
        vals = [raw[d] / self.temperature for d in depts]
        m = max(vals) if vals else 0.0
        exps = [math.exp(v - m) for v in vals]
        s = sum(exps) or 1.0
        return [DeptCandidate(dept=d, confidence=e / s) for d, e in zip(depts, exps)]

    def _filter_candidates(self, candidates: List[DeptCandidate]) -> List[DeptCandidate]:
        """Top-K 截断 + tau_keep 阈值过滤. 至少保留 1 个候选 (留给 ambiguous 判定/fallback)."""
        if not candidates:
            return candidates
        topk = candidates[: self.top_k_keep]
        kept = [c for c in topk if c.confidence >= self.tau_keep]
        if not kept:
            kept = [topk[0]]
        return kept

    def _classify(self, candidates: List[DeptCandidate]) -> str:
        if not candidates:
            return "ambiguous"
        top1 = candidates[0].confidence
        top2 = candidates[1].confidence if len(candidates) > 1 else 0.0
        if top1 < self.tau:
            return "ambiguous"
        if top1 - top2 > self.margin:
            return "single_clear"
        return "multi_cross"


def _hit_to_dict(h: Hit) -> dict:
    return {
        "dept": h.dept,
        "score": round(h.score, 4),
        "text": h.text[:80],  # 截断, 避免日志膨胀
        "source_path": h.source_path,
    }
