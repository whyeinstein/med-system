"""关键词 + 正则安全规则引擎 (论文 4.3.6).

从 config/safety_rules.yaml 读取:
  - high_risk_patterns: [{pattern, category, replacement}, ...]
  - low_risk_patterns:  [{pattern, category}, ...]
  - disclaimer_template / enhanced_disclaimer_template

扫描范围: FinalReport.summary + 每条 DepartmentOpinion 的四段文本.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import yaml

from app.schemas.report import FinalReport


def _collect_texts(report: FinalReport) -> List[str]:
    texts = [report.summary or ""]
    for op in report.dept_opinions:
        texts.extend([op.diagnosis, op.differential, op.treatment, op.attention])
    return texts


class SafetyChecker:
    def __init__(self, rules_path: str, low_risk_threshold: int = 2) -> None:
        self.rules_path = rules_path
        self.low_risk_threshold = low_risk_threshold
        self._high: List[dict] = []
        self._low: List[dict] = []
        self.disclaimer_template: str = ""
        self.enhanced_disclaimer_template: str = ""
        self._load()

    def _load(self) -> None:
        path = Path(self.rules_path)
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        self._high = [
            {
                "pattern": re.compile(r["pattern"]),
                "category": r.get("category", "high"),
                "replacement": r.get("replacement", ""),
                "raw": r["pattern"],
            }
            for r in data.get("high_risk_patterns", [])
        ]
        self._low = [
            {
                "pattern": re.compile(r["pattern"]),
                "category": r.get("category", "low"),
                "raw": r["pattern"],
            }
            for r in data.get("low_risk_patterns", [])
        ]
        self.disclaimer_template = data.get("disclaimer_template", "").strip()
        self.enhanced_disclaimer_template = data.get(
            "enhanced_disclaimer_template", ""
        ).strip()

    @property
    def high_rules(self) -> List[dict]:
        return self._high

    def check(self, report: FinalReport) -> dict:
        """返回 {hits: [...], high_risk: bool, low_risk_count: int}."""
        hits: List[dict] = []
        low_count = 0
        for text in _collect_texts(report):
            if not text:
                continue
            for rule in self._high:
                for m in rule["pattern"].finditer(text):
                    hits.append(
                        {
                            "level": "high",
                            "category": rule["category"],
                            "match": m.group(0),
                            "pattern": rule["raw"],
                        }
                    )
            for rule in self._low:
                low_count += len(list(rule["pattern"].finditer(text)))
        return {
            "hits": hits,
            "high_risk": bool(hits),
            "low_risk_count": low_count,
            "accumulated_high": low_count >= self.low_risk_threshold,
        }

