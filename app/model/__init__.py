"""模型能力层. 对上游 (agents/coordinator) 只暴露 `ModelEngine.generate`."""
from app.model.inference import ModelEngine

__all__ = ["ModelEngine"]
