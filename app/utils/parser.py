"""科室意见文本的五字段正则解析. 阶段 2 agent 层使用, 此处先备好."""
from __future__ import annotations

import re
from typing import Dict

_FIELD_PATTERNS = {
    "diagnosis": r"诊断倾向[::]\s*(.+?)(?=\n[\u4e00-\u9fa5]+[::]|\Z)",
    "differential": r"鉴别要点[::]\s*(.+?)(?=\n[\u4e00-\u9fa5]+[::]|\Z)",
    "treatment": r"处置建议[::]\s*(.+?)(?=\n[\u4e00-\u9fa5]+[::]|\Z)",
    "attention": r"关注事项[::]\s*(.+?)(?=\n[\u4e00-\u9fa5]+[::]|\Z)",
    "self_confidence": r"自评置信度[::]\s*(high|medium|low)",
}


def parse_opinion_text(text: str) -> Dict[str, str]:
    """将 LLM 输出解析为五字段 dict. 缺字段时返回空串, 由上层决定是否重试."""
    out: Dict[str, str] = {}
    for key, pat in _FIELD_PATTERNS.items():
        m = re.search(pat, text, flags=re.DOTALL | re.IGNORECASE)
        out[key] = m.group(1).strip() if m else ""
    # self_confidence 兜底
    sc = out.get("self_confidence", "").lower()
    if sc not in {"high", "medium", "low"}:
        out["self_confidence"] = "medium"
    return out


def completeness_score(fields: Dict[str, str]) -> float:
    """五字段覆盖度评分, 每缺一字段线性扣分. 供 aggregator L2 使用."""
    keys = ["diagnosis", "differential", "treatment", "attention", "self_confidence"]
    filled = sum(1 for k in keys if fields.get(k))
    return filled / len(keys)
