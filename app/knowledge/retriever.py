"""FAISS 检索器. 使用 IndexFlatIP (向量需归一化, 等价余弦相似度)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np

from app.knowledge.embedder import Embedder
from app.knowledge.kb_loader import Document


@dataclass
class Hit:
    text: str
    dept: str
    score: float
    source_path: str


class FaissRetriever:
    INDEX_FILE = "faiss.index"
    DOCS_FILE = "docs.jsonl"

    def __init__(self, embedder: Embedder) -> None:
        import faiss  # noqa: F401 延迟导入, 便于无 faiss 环境也能 import 本模块检查签名

        self.embedder = embedder
        self._index = None
        self._docs: List[Document] = []

    # ---------------- build / persist ----------------

    def build(self, docs: List[Document]) -> None:
        import faiss

        if not docs:
            raise ValueError("build() 收到空 docs 列表, 请先准备知识库文本")
        texts = [d.text for d in docs]
        vecs = self.embedder.encode(texts)  # (N, D) float32, 已归一化
        dim = vecs.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vecs)
        self._index = index
        self._docs = list(docs)

    def save(self, dir_path: str | Path) -> None:
        import faiss

        if self._index is None:
            raise RuntimeError("尚未 build, 无法 save")
        out = Path(dir_path)
        out.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(out / self.INDEX_FILE))
        with (out / self.DOCS_FILE).open("w", encoding="utf-8") as fh:
            for d in self._docs:
                fh.write(json.dumps(d.to_dict(), ensure_ascii=False) + "\n")

    def load(self, dir_path: str | Path) -> None:
        import faiss

        p = Path(dir_path)
        self._index = faiss.read_index(str(p / self.INDEX_FILE))
        self._docs = []
        with (p / self.DOCS_FILE).open("r", encoding="utf-8") as fh:
            for line in fh:
                obj = json.loads(line)
                self._docs.append(Document(**obj))

    # ---------------- search ----------------

    def search(self, query: str, top_k: int = 10) -> List[Hit]:
        if self._index is None:
            raise RuntimeError("索引未初始化, 请先 build() 或 load()")
        vec = self.embedder.encode([query])  # (1, D)
        scores, idxs = self._index.search(vec, top_k)
        hits: List[Hit] = []
        for score, idx in zip(scores[0].tolist(), idxs[0].tolist()):
            if idx < 0 or idx >= len(self._docs):
                continue
            d = self._docs[idx]
            hits.append(
                Hit(text=d.text, dept=d.dept, score=float(score), source_path=d.source_path)
            )
        return hits

    @property
    def size(self) -> int:
        return len(self._docs)
