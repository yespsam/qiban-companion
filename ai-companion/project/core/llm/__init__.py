"""LLM 后端工厂（SPEC §3.4）。

create_backend(settings) 按 settings.llm_backend 返回对应后端实例；
各后端模块在工厂函数内懒加载，保证无 GPU/无网络环境也能 import 本包。
"""
from __future__ import annotations

from core.llm.base import GenerateResult, LLMBackend

__all__ = ["GenerateResult", "LLMBackend", "create_backend"]


def create_backend(settings) -> LLMBackend:
    """按 settings.llm_backend 创建后端：llamacpp | ollama | mock。"""
    name = str(getattr(settings, "llm_backend", "mock") or "mock").lower()
    if name == "llamacpp":
        from core.llm.llamacpp_backend import LlamaCppBackend  # 懒加载

        return LlamaCppBackend(settings)
    if name == "ollama":
        from core.llm.ollama_backend import OllamaBackend  # 懒加载

        return OllamaBackend(settings)
    if name == "mock":
        from core.llm.mock_backend import MockBackend  # 懒加载

        return MockBackend(settings)
    raise ValueError(
        f"未知 llm_backend: {name!r}（可选: llamacpp | ollama | mock）"
    )
