"""OpenAI 兼容云端后端（SPEC §3.4 扩展）。

- 未配置 Key：health_check=False，generate 抛出带配置指引的 RuntimeError；
- 请求体遵循 OpenAI Chat Completions 契约（model/messages/temperature/max_tokens）；
- 响应解析 content 与 reasoning_content（Kimi/DeepSeek 风格）；
- 网络/HTTP 错误转成带排查指引的 RuntimeError；
- 工厂 create_backend 接受 openai | openai_compat | cloud 别名。
"""
import json

import pytest

from core.config import Settings
from core.llm import create_backend
from core.llm.openai_compat_backend import OpenAICompatBackend


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    """记录请求体的假 httpx.Client。"""
    last_payload = None
    last_url = None
    response = None
    fail = None

    def __init__(self, base_url=None, timeout=None, headers=None):
        self.base_url = base_url
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None):
        type(self).last_url = url
        type(self).last_payload = json
        if type(self).fail:
            raise type(self).fail
        return type(self).response

    def get(self, url, timeout=None):
        if type(self).fail:
            raise type(self).fail
        return type(self).response


def _backend(monkeypatch, **env):
    for key in ("QIBAN_LLM_API_KEY", "OPENAI_API_KEY",
                "QIBAN_LLM_BASE_URL", "OPENAI_BASE_URL",
                "QIBAN_LLM_MODEL", "OPENAI_MODEL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    backend = OpenAICompatBackend(Settings())
    monkeypatch.setattr(backend, "_client", lambda: _FakeClient())
    return backend


_OK_PAYLOAD = {
    "choices": [{"message": {"content": "<think>他来了，开心。</think>主人好呀！",
                             "reasoning_content": "内心推理"}}],
    "usage": {"total_tokens": 42},
}


# ------------------------------------------------------------------ 配置与契约
def test_health_check_false_without_key(monkeypatch):
    backend = _backend(monkeypatch)
    assert backend.api_key == ""
    assert backend.health_check() is False


def test_generate_requires_key(monkeypatch):
    backend = _backend(monkeypatch)
    with pytest.raises(RuntimeError, match="QIBAN_LLM_API_KEY"):
        backend.generate([{"role": "user", "content": "在吗"}])


def test_generate_payload_and_parse(monkeypatch):
    _FakeClient.response = _FakeResponse(_OK_PAYLOAD)
    _FakeClient.fail = None
    backend = _backend(monkeypatch, QIBAN_LLM_API_KEY="sk-test",
                       QIBAN_LLM_MODEL="kimi-k2")
    result = backend.generate([{"role": "user", "content": "在吗"}],
                              temperature=0.8, max_tokens=500)
    payload = _FakeClient.last_payload
    assert _FakeClient.last_url == "/chat/completions"
    assert payload["model"] == "kimi-k2"
    assert payload["messages"][0]["content"] == "在吗"
    assert payload["temperature"] == 0.8 and payload["max_tokens"] == 500
    assert payload["stream"] is False
    assert "<think>" in result.text
    assert result.reasoning == "内心推理"
    assert result.tokens == 42 and result.model == "openai:kimi-k2"


def test_generate_network_error_has_guidance(monkeypatch):
    _FakeClient.response = None
    _FakeClient.fail = ConnectionError("refused")
    backend = _backend(monkeypatch, QIBAN_LLM_API_KEY="sk-test")
    with pytest.raises(RuntimeError, match="云端 LLM 请求失败"):
        backend.generate([{"role": "user", "content": "在吗"}])
    _FakeClient.fail = None


def test_env_fallback_openai_vars(monkeypatch):
    backend = _backend(monkeypatch, OPENAI_API_KEY="sk-openai",
                       OPENAI_BASE_URL="https://api.deepseek.com/v1",
                       OPENAI_MODEL="deepseek-chat")
    assert backend.api_key == "sk-openai"
    assert backend.base_url == "https://api.deepseek.com/v1"
    assert backend.model == "deepseek-chat"


def test_default_base_url_and_model(monkeypatch):
    backend = _backend(monkeypatch, QIBAN_LLM_API_KEY="sk-test")
    assert backend.base_url == "https://api.moonshot.cn/v1"
    assert backend.model == "kimi-k2.5"


# ------------------------------------------------------------------ 工厂
@pytest.mark.parametrize("name", ["openai", "openai_compat", "cloud"])
def test_factory_aliases(name):
    backend = create_backend(Settings(llm_backend=name))
    assert isinstance(backend, OpenAICompatBackend)


def test_factory_unknown_still_raises():
    with pytest.raises(ValueError):
        create_backend(Settings(llm_backend="nonexistent"))


# ------------------------------------------------------------------ 自动降级
def test_fallback_to_mock_when_openai_unhealthy(monkeypatch):
    """openai 无 Key 时自动回退 mock，保证开箱即聊。"""
    for key in ("QIBAN_LLM_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    from core.llm import create_backend_with_fallback
    from core.llm.mock_backend import MockBackend
    backend = create_backend_with_fallback(Settings(llm_backend="openai"))
    assert isinstance(backend, MockBackend)
    result = backend.generate([{"role": "user", "content": "在吗"}])
    assert result.text.startswith("<think>")


def test_fallback_keeps_healthy_openai(monkeypatch):
    """openai 健康检查通过时不做降级，原样使用云端后端。"""
    monkeypatch.setenv("QIBAN_LLM_API_KEY", "sk-test")
    monkeypatch.setattr(OpenAICompatBackend, "health_check", lambda self: True)
    from core.llm import create_backend_with_fallback
    backend = create_backend_with_fallback(Settings(llm_backend="openai"))
    assert backend.name == "openai"
