"""临床知识库: 文本加载 → 向量化 → FAISS 检索."""
from app.knowledge.kb_loader import load_kb, Document
from app.knowledge.embedder import Embedder, get_default_embedder
from app.knowledge.retriever import FaissRetriever, Hit

__all__ = [
    "load_kb",
    "Document",
    "Embedder",
    "get_default_embedder",
    "FaissRetriever",
    "Hit",
]
