"""L1 一致性检验: 对各科室 diagnosis 文本做嵌入, 取两两余弦 **最小值** (非均值).

论文 4.3.5 第一级. 医疗场景对冲突零容忍, 只要有一对意见显著偏离就进下一级.
"""
from __future__ import annotations

from typing import List, Tuple

import numpy as np

from app.schemas.opinion import DepartmentOpinion


def consistency_check(
    opinions: List[DepartmentOpinion], embedder, tau: float
) -> Tuple[bool, float]:
    """返回 (是否通过 L1, 一致性最小余弦分数 S_consist).

    - 少于 2 条意见: 视为天然一致, S=1.0
    - 嵌入器输出默认归一化, 内积即余弦
    """
    texts = [op.diagnosis.strip() for op in opinions if op.diagnosis.strip()]
    if len(texts) < 2:
        return True, 1.0

    vecs = embedder.encode(texts)
    vecs = np.asarray(vecs, dtype=np.float32)
    # 保险: 再归一化一次, 避免 embedder.normalize 被关闭时出错
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = vecs / norms

    sims = vecs @ vecs.T  # (N, N)
    n = sims.shape[0]
    # 取上三角 (不含对角) 的最小值
    iu = np.triu_indices(n, k=1)
    s_min = float(sims[iu].min())
    return s_min >= tau, s_min

