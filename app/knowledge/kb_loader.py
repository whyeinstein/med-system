"""按科室子目录扫描 .txt, 段落切分后输出 Document 列表."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List


@dataclass
class Document:
    text: str
    dept: str
    source_path: str

    def to_dict(self) -> Dict:
        return asdict(self)


def _split_chunks(text: str, chunk_size: int = 256, overlap: int = 32) -> List[str]:
    """按字符长度定窗切分 (中文字符粒度), 保留段落边界优先."""
    text = text.strip()
    if not text:
        return []
    # 优先按空行切段
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    for para in paragraphs:
        if len(para) <= chunk_size:
            chunks.append(para)
            continue
        i = 0
        while i < len(para):
            chunks.append(para[i : i + chunk_size])
            i += chunk_size - overlap
    return chunks


def load_kb(
    kb_root: str | Path,
    chunk_size: int = 256,
    overlap: int = 32,
) -> List[Document]:
    """遍历 `kb_root/<dept>/*.txt`, 切分后返回 Document 列表. dept 即子目录名."""
    root = Path(kb_root)
    if not root.exists():
        raise FileNotFoundError(f"知识库目录不存在: {root}")

    docs: List[Document] = []
    for dept_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        dept = dept_dir.name
        for fp in sorted(dept_dir.glob("*.txt")):
            text = fp.read_text(encoding="utf-8", errors="ignore")
            for chunk in _split_chunks(text, chunk_size, overlap):
                docs.append(Document(text=chunk, dept=dept, source_path=str(fp)))
    return docs


def iter_texts(docs: Iterable[Document]) -> List[str]:
    return [d.text for d in docs]
