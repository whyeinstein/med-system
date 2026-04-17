"""文本向量化封装. 默认 BGE-base-zh-v1.5, 支持本地路径与在线名称.

为降低环境耦合, 优先使用 `sentence-transformers`; 若不可用则退回 `transformers` + mean-pooling.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

import numpy as np


class Embedder:
    def __init__(
        self,
        model_name_or_path: str = "BAAI/bge-base-zh-v1.5",
        device: str = "cpu",
        batch_size: int = 16,
        normalize: bool = True,
    ) -> None:
        self.model_name_or_path = model_name_or_path
        self.device = device
        self.batch_size = batch_size
        self.normalize = normalize
        self._backend: str = ""
        self._st_model = None
        self._hf_model = None
        self._hf_tokenizer = None
        self._load()

    def _load(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._st_model = SentenceTransformer(
                self.model_name_or_path, device=self.device
            )
            self._backend = "sentence-transformers"
            return
        except Exception:  # noqa: BLE001
            pass

        # 退化: transformers + mean pooling
        from transformers import AutoModel, AutoTokenizer  # type: ignore

        self._hf_tokenizer = AutoTokenizer.from_pretrained(self.model_name_or_path)
        self._hf_model = AutoModel.from_pretrained(self.model_name_or_path).to(self.device)
        self._hf_model.eval()
        self._backend = "transformers"

    def encode(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)

        if self._backend == "sentence-transformers":
            vecs = self._st_model.encode(  # type: ignore[union-attr]
                texts,
                batch_size=self.batch_size,
                normalize_embeddings=self.normalize,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            return vecs.astype(np.float32)

        # transformers fallback
        import torch  # type: ignore

        all_vecs: List[np.ndarray] = []
        with torch.no_grad():
            for i in range(0, len(texts), self.batch_size):
                batch = texts[i : i + self.batch_size]
                enc = self._hf_tokenizer(  # type: ignore[union-attr]
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=512,
                    return_tensors="pt",
                ).to(self.device)
                out = self._hf_model(**enc)  # type: ignore[union-attr]
                last = out.last_hidden_state  # (B, L, D)
                mask = enc["attention_mask"].unsqueeze(-1).float()
                pooled = (last * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1e-6)
                if self.normalize:
                    pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
                all_vecs.append(pooled.cpu().numpy().astype(np.float32))
        return np.concatenate(all_vecs, axis=0)

    @property
    def dim(self) -> int:
        if self._backend == "sentence-transformers":
            return int(self._st_model.get_sentence_embedding_dimension())  # type: ignore[union-attr]
        return int(self._hf_model.config.hidden_size)  # type: ignore[union-attr]


@lru_cache(maxsize=4)
def get_default_embedder(
    model_name_or_path: str = "BAAI/bge-base-zh-v1.5",
    device: str = "cpu",
) -> Embedder:
    """进程内单例, 避免重复加载权重."""
    return Embedder(model_name_or_path=model_name_or_path, device=device)
