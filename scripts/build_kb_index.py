"""构建 FAISS 知识库索引.

使用:
    python scripts/build_kb_index.py --kb data/knowledge_base --out data/faiss_index
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.knowledge.embedder import get_default_embedder  # noqa: E402
from app.knowledge.kb_loader import load_kb  # noqa: E402
from app.knowledge.retriever import FaissRetriever  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb", default="data/knowledge_base", help="知识库根目录")
    parser.add_argument("--out", default="data/faiss_index", help="索引输出目录")
    parser.add_argument("--config", default="config/settings.yaml")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    emb_cfg = cfg["embedder"]
    retr_cfg = cfg["retriever"]

    docs = load_kb(
        args.kb,
        chunk_size=retr_cfg.get("chunk_size", 256),
        overlap=retr_cfg.get("chunk_overlap", 32),
    )
    if not docs:
        raise SystemExit(f"[build_kb_index] 未在 {args.kb} 下扫描到任何 .txt 文档")

    print(f"[build_kb_index] loaded {len(docs)} chunks, dept counts:")
    dept_counts: dict[str, int] = {}
    for d in docs:
        dept_counts[d.dept] = dept_counts.get(d.dept, 0) + 1
    for k, v in sorted(dept_counts.items()):
        print(f"  - {k}: {v}")

    embedder = get_default_embedder(
        model_name_or_path=emb_cfg["model_name_or_path"],
        device=emb_cfg.get("device", "cpu"),
    )
    retriever = FaissRetriever(embedder)
    retriever.build(docs)
    retriever.save(args.out)
    print(f"[build_kb_index] saved index to {args.out} (size={retriever.size})")


if __name__ == "__main__":
    main()
