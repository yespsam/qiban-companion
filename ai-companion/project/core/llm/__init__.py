"""LLM 后端工厂（SPEC §3.4）。

create_backend(settings) 按 settings.llm_backend 返回对应后端实例；
create_backend_with_fallback(settings) 在其之上加健康检查，后端不可用
（无 Key / 无模型文件 / 服务未启动）时自动回退 mock 罐头模板，保证开箱即聊。
各后端模块在工厂函数内懒加载，保证无 GPU/无网络环境也能 import 本包。
"""
from __future__ import annotations

from core.llm.base import GenerateResult, LLMBackend
from core.logging_utils import get_logger

__all__ = ["GenerateResult", "LLMBackend", "create_backend", "create_backend_with_fallback"]

log = get_logger(__name__)


def create_backend(settings) -> LLMBackend:
    """按 settings.llm_backend 创建后端：llamacpp | ollama | openai | mock。"""
    name = str(getattr(settings, "llm_backend", "mock") or "mock").lower()
    if name == "llamacpp":
        from core.llm.llamacpp_backend import LlamaCppBackend  # 懒加载

        return LlamaCppBackend(settings)
    if name == "ollama":
        from core.llm.ollama_backend import OllamaBackend  # 懒加载

        return OllamaBackend(settings)
    if name in ("openai", "openai_compat", "cloud"):
        from core.llm.openai_compat_backend import OpenAICompatBackend  # 懒加载

        return OpenAICompatBackend(settings)
    if name == "mock":
        from core.llm.mock_backend import MockBackend  # 懒加载

        return MockBackend(settings)
    raise ValueError(
        f"未知 llm_backend: {name!r}（可选: llamacpp | ollama | openai | mock）"
    )


def create_backend_with_fallback(settings) -> LLMBackend:
    """按配置创建后端；健康检查失败时回退 mock，保证开箱即聊。

    例如默认 llm_backend=openai 但没配 QIBAN_LLM_API_KEY 时，
    自动退回罐头模板并给出 warning，而不是让对话直接报错。
    """
    backend = create_backend(settings)
    if backend.name == "mock":
        return backend
    try:
        healthy = backend.health_check()
    except Exception:  # noqa: BLE001 - 探测异常同样视为不可用
        healthy = False
    if healthy:
        return backend
    log.warning(
        "LLM 后端 %s 不可用（未配置/未启动），本次会话回退为 mock 罐头模板。"
        "配置方法见 config/settings.yaml 注释。",
        backend.name,
    )
    from core.llm.mock_backend import MockBackend  # 懒加载

    return MockBackend(settings)
