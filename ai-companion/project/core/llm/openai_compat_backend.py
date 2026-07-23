"""OpenAI 兼容云端后端（SPEC §3.4 扩展）：接入 Kimi/DeepSeek/OpenAI 等
任何 OpenAI Chat Completions 兼容接口，让人物真正按主人的话生成回应，
而不是走本地罐头模板。

配置（环境变量，优先级从高到低）：
    QIBAN_LLM_API_KEY  / OPENAI_API_KEY      —— API Key（必填）
    QIBAN_LLM_BASE_URL / OPENAI_BASE_URL     —— 接口地址，默认 https://api.moonshot.cn/v1
    QIBAN_LLM_MODEL    / OPENAI_MODEL        —— 模型名，默认 moonshot-v1-8k

httpx 懒加载；未配置 Key 时 health_check 返回 False，
generate 抛出带清晰指引的 RuntimeError（交由上层回退 mock）。
"""
from __future__ import annotations

import json
import os
from typing import Iterator

from core.llm.base import GenerateResult, LLMBackend
from core.logging_utils import get_logger

log = get_logger(__name__)

_DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
_DEFAULT_MODEL = "moonshot-v1-8k"


def _env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
    return ""


class OpenAICompatBackend(LLMBackend):
    name = "openai"

    def __init__(self, settings=None, base_url: str | None = None,
                 api_key: str | None = None, model: str | None = None):
        self.base_url = (base_url or _env("QIBAN_LLM_BASE_URL", "OPENAI_BASE_URL")
                         or _DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or _env("QIBAN_LLM_API_KEY", "OPENAI_API_KEY")
        # 云端模型名只取显式传入或环境变量——settings.model_id 是本地 GGUF
        # 注册表 id（如 hermes-3-8b），不是云端模型名，不能混用。
        self.model = model or _env("QIBAN_LLM_MODEL", "OPENAI_MODEL") or _DEFAULT_MODEL

    # ------------------------------------------------------------ 基础设施
    def _client(self):
        import httpx  # 懒加载

        return httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(120.0, connect=15.0),
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    def _require_key(self) -> None:
        if not self.api_key:
            raise RuntimeError(
                "未配置云端 LLM Key：请设置环境变量 QIBAN_LLM_API_KEY"
                "（或 OPENAI_API_KEY），可选 QIBAN_LLM_BASE_URL / QIBAN_LLM_MODEL；"
                "或把 config/settings.yaml 的 llm_backend 改回 mock / llamacpp / ollama。"
            )

    # ------------------------------------------------------------ 契约
    def generate(self, messages: list[dict], temperature: float = 0.7,
                 max_tokens: int = 1024) -> GenerateResult:
        self._require_key()
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            with self._client() as client:
                resp = client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except RuntimeError:
            raise
        except Exception as exc:  # noqa: BLE001 - 转成带指引的错误
            raise RuntimeError(
                f"云端 LLM 请求失败（{self.base_url}）：{exc}。"
                "检查网络、Key 是否有效、额度是否充足。"
            ) from exc
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        text = str(message.get("content") or "")
        reasoning = str(message.get("reasoning_content") or "")
        usage = data.get("usage") or {}
        tokens = int(usage.get("total_tokens") or max(1, len(text) // 2))
        return GenerateResult(text=text, reasoning=reasoning,
                              model=f"openai:{self.model}", tokens=tokens)

    def generate_stream(self, messages: list[dict], temperature: float = 0.7,
                        max_tokens: int = 1024, **kw) -> Iterator[dict]:
        self._require_key()
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        with self._client() as client:
            with client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    think = delta.get("reasoning_content")
                    if think:
                        yield {"type": "thinking", "delta": str(think)}
                    content = delta.get("content")
                    if content:
                        yield {"type": "text", "delta": str(content)}

    def health_check(self) -> bool:
        if not self.api_key:
            return False
        try:
            with self._client() as client:
                resp = client.get("/models", timeout=10.0)
                return resp.status_code < 500
        except Exception:  # noqa: BLE001 - 无网络/服务不可达
            return False
