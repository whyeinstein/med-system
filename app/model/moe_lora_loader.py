"""MoE-LoRA 模型加载器（阶段 7）。

将 qwen25_3b_moelora_qv 训练产出的 moelora_state.pt 注入 Qwen2.5-3B-Instruct 基座。
超参与训练配置 configs/qwen25_3b_moelora_qv.yaml 保持一致：
  num_experts=7, r_max=32, rank_bins=[8,16,24,32], target_modules=[q_proj, v_proj]

返回 (wrapper, tokenizer)：
  wrapper  — MoELoRAWrapper，generate 时走 wrapper.base_model.generate()
  tokenizer — 与基座匹配的分词器
"""
from __future__ import annotations

import os
import sys

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from app.utils.logger import get_logger

_LOG = get_logger("model.moe_lora_loader")

# 与训练配置 qwen25_3b_moelora_qv.yaml 保持严格一致
_DEPT2ID: dict = {
    "general": 0,
    "im": 1,
    "surgical": 2,
    "pediatric": 3,
    "oagd": 4,
    "andriatria": 5,
    "oncology": 6,
}
_NUM_EXPERTS = 7
_R_MAX = 32
_RANK_BINS = [8, 16, 24, 32]
_LORA_ALPHA = 16.0
_TARGET_MODULES = ["q_proj", "v_proj"]
_MOELORA_SRC = "/root/autodl-tmp/moelora-med/src"


def _ensure_moelora_src() -> None:
    """将 moelora-med/src 加入 sys.path（幂等）。"""
    if not os.path.isdir(_MOELORA_SRC):
        raise FileNotFoundError(
            f"moelora-med/src 目录不存在: {_MOELORA_SRC}。"
            "请确认 moelora-med 项目位于 /root/autodl-tmp/moelora-med/。"
        )
    if _MOELORA_SRC not in sys.path:
        sys.path.insert(0, _MOELORA_SRC)


def load_moe_lora_model(
    base_model_path: str,
    lora_adapter_path: str,
    device_map: str = "auto",
    dtype: str = "bfloat16",
):
    """加载 Qwen2.5-3B-Instruct + MoE-LoRA，返回 (wrapper, tokenizer)。

    Args:
        base_model_path:   Qwen2.5-3B-Instruct 基座目录
        lora_adapter_path: 包含 moelora_state.pt 的检查点目录（best/ 或 final_calibrated/）
        device_map:        "auto" 自动分配 GPU，或 "cpu"
        dtype:             "bfloat16" / "float16" / "float32"
    """
    _ensure_moelora_src()

    # 训练侧模块，通过 sys.path 动态导入，不污染 app 包命名空间
    from model.patch import replace_target_linears  # type: ignore[import]
    from model.wrapper import MoELoRAWrapper  # type: ignore[import]

    torch_dtype = getattr(torch, dtype)

    # 1. 分词器
    tokenizer = AutoTokenizer.from_pretrained(base_model_path, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    _LOG.info("tokenizer loaded from %s", base_model_path)

    # 2. 基座模型
    base = AutoModelForCausalLM.from_pretrained(
        base_model_path,
        dtype=torch_dtype,
        device_map=device_map,
        trust_remote_code=True,
    )
    _LOG.info("base model loaded: %s layers", base.config.num_hidden_layers)

    # 3. 将 q_proj / v_proj 替换为 MoELoRALinear
    n_replaced = replace_target_linears(
        base,
        target_keywords=_TARGET_MODULES,
        num_experts=_NUM_EXPERTS,
        r_max=_R_MAX,
        lora_alpha=_LORA_ALPHA,
        dropout=0.0,  # 推理阶段不使用 dropout
    )
    _LOG.info("replaced %s linear layers with MoELoRALinear", n_replaced)

    # 4. 包装为 MoELoRAWrapper
    wrapper = MoELoRAWrapper(
        base_model=base,
        hidden_size=base.config.hidden_size,
        dept2id=_DEPT2ID,
        rank_bins=_RANK_BINS,
    ).eval()

    # 5. 加载 MoE-LoRA 权重（仅 LoRA 参数 + router/ranker，不含基座权重）
    state_path = os.path.join(lora_adapter_path, "moelora_state.pt")
    if not os.path.exists(state_path):
        raise FileNotFoundError(f"moelora_state.pt 不存在: {state_path}")

    sd = torch.load(state_path, map_location="cpu", weights_only=True)
    missing, unexpected = wrapper.load_state_dict(sd, strict=False)
    # missing 为基座权重（未保存到 state.pt，符合预期）；unexpected 应为空
    if unexpected:
        _LOG.warning("moelora_state.pt 含未预期的 key（前 5 个）: %s", unexpected[:5])

    n_lora = sum(1 for k in sd if k.startswith("base_model"))
    n_global = len(sd) - n_lora
    _LOG.info(
        "MoE-LoRA state loaded: %s per-layer LoRA keys, %s global (router/ranker) keys",
        n_lora,
        n_global,
    )

    return wrapper, tokenizer
