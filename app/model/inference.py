"""MoE-LoRA 模型推理引擎. mock 模式供阶段 0~6 使用, 真实模式在阶段 7 接入.

**重要**: 动态秩的秩档位映射是本文件 `_estimate_rank` 的内部步骤, 不是独立模块.
仲裁由协调器显式传入 `rank_hint=max(rank_bins)`, 参见论文 4.3.5 第三级.
"""
from __future__ import annotations

import random
import time
from typing import Optional, Tuple

from app.utils.logger import get_logger, log_with

_LOG = get_logger("model.inference")

_MOCK_TEMPLATE = (
    "诊断倾向: 根据主诉与症状, 考虑为 {dept_hint}相关常见病 (mock).\n"
    "鉴别要点: 需鉴别 mock 疾病 A / mock 疾病 B, 依据实验室检查差异.\n"
    "处置建议: 建议完善相关检查, 对症处理, 必要时专科会诊 (mock).\n"
    "关注事项: 密切观察生命体征与症状演变 (mock).\n"
    "自评置信度: medium\n"
)


class ModelEngine:
    """统一推理入口. mock=True 时仅产生合法格式的伪输出, 不加载任何权重."""

    def __init__(
        self,
        checkpoint_path: str = "",
        rank_bins: Tuple[int, ...] = (8, 16, 24, 32),
        default_rank: int = 16,
        mock: bool = True,
    ) -> None:
        self.checkpoint_path = checkpoint_path
        self.rank_bins = tuple(rank_bins)
        self.default_rank = default_rank
        self.mock = mock
        if not mock:
            # 阶段 7: 通过 moe_lora_loader 加载真实模型
            from app.model.moe_lora_loader import load_moe_lora_model

            self._model, self._tokenizer = load_moe_lora_model(checkpoint_path)
        else:
            self._model = None
            self._tokenizer = None
            log_with(_LOG, "info", "ModelEngine initialized in MOCK mode")

    # ---------------- public ----------------

    def generate(
        self,
        prompt: str,
        rank_hint: Optional[int] = None,
        max_new_tokens: int = 1024,
    ) -> Tuple[str, dict]:
        """返回 (text, meta). meta 含 rank/router_weights/elapsed_ms, 供可视化追溯."""
        t0 = time.perf_counter()
        rank = rank_hint if rank_hint is not None else self._estimate_rank(prompt)

        if self.mock:
            dept_hint = self._guess_dept_from_prompt(prompt)
            # 轻微延迟模拟推理, 便于耗时字段非零
            time.sleep(random.uniform(0.02, 0.08))
            text = _MOCK_TEMPLATE.format(dept_hint=dept_hint)
            router_weights = self._mock_router_weights()
        else:
            text, router_weights = self._real_generate(prompt, rank, max_new_tokens)

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        meta = {
            "rank": rank,
            "router_weights": router_weights,
            "elapsed_ms": round(elapsed_ms, 2),
            "mock": self.mock,
        }
        return text, meta

    # ---------------- internal ----------------

    def _estimate_rank(self, prompt: str) -> int:
        """mock 模式返回默认档位; 真实模式按论文: 基座前向 → token 级 CE 均值 → 归一化 → 映射档位."""
        if self.mock:
            return self.default_rank
        raise NotImplementedError("Phase 7: 困惑度驱动动态秩估计")

    @staticmethod
    def _guess_dept_from_prompt(prompt: str) -> str:
        """仅用于 mock 输出, 让 text 更像是该科室产出的内容."""
        for needle, hint in (
            ("儿科", "儿科"),
            ("外科", "外科"),
            ("内科", "内科"),
            ("通用", "全科"),
        ):
            if needle in prompt:
                return hint
        return "本科"

    def _mock_router_weights(self) -> dict:
        """伪造层内专家路由权重摘要, 格式与真实模型保持一致."""
        experts = ["E1", "E2", "E3", "E4"]
        raw = [random.random() for _ in experts]
        s = sum(raw) or 1.0
        return {e: round(v / s, 4) for e, v in zip(experts, raw)}

    def _real_generate(
        self, prompt: str, rank: int, max_new_tokens: int
    ) -> Tuple[str, dict]:
        raise NotImplementedError("Phase 7: 真实 MoE-LoRA 推理 + 秩注入")
