"""Ollama 后端（SPEC §3.4）：http://localhost:11434/api/chat，think:true 支持推理模型。

httpx 懒加载；无网络 / Ollama 未启动时 health_check 返回 False，
generate 抛出带清晰指引的 RuntimeError。
"""
from __future__ import annotations

import json
import os
from typing import Iterator

import yaml

from core.llm.base import GenerateResult, LLMBackend
from core.logging_utils import get_logger

log = get_logger(__name__)

_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaBackend(LLMBackend):
    name = "ollama"

    def __init__(self, settings=None, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or os.environ.get("OLLAMA_HOST")
                         or _DEFAULT_BASE_URL).rstrip("/")
        self.model = model or self._resolve_model(settings) or "hermes3:8b"

    @staticmethod
    def _resolve_model(settings) -> str:
        """model_id → models.yaml 里的 ollama_tag；没有则直接用 model_id。"""
        model_id = getattr(settings, "model_id", "") if settings else ""
        try:
            with open("config/models.yaml", "r", encoding="utf-8") as f:
                registry = yaml.safe_load(f) or {}
            entry = (registry.get("models") or {}).get(model_id) or {}
            return str(entry.get("ollama_tag") or model_id)
        except Exception:  # noqa: BLE001 - 注册表缺失时退化为 model_id
            return model_id

    def _client(self):
        import httpx  # 懒加载

        return httpx.Client(base_url=self.base_url, timeout=120.0)

    def generate(self, messages: list[dict], temperature: float = 0.7,
                 max_tokens: int = 1024) -> GenerateResult:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": True,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            with self._client() as client:
                resp = client.post("/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Ollama 调用失败（{self.base_url}）：{exc}。"
                "请确认已运行 `ollama serve` 并 `ollama pull " + self.model + "`"
            ) from exc
        msg = data.get("message") or {}
        reasoning = str(msg.get("thinking") or msg.get("reasoning") or "")
        text = str(msg.get("content") or "")
        tokens = int(data.get("eval_count") or 0) + int(data.get("prompt_eval_count") or 0)
        return GenerateResult(text=text, reasoning=reasoning,
                              model=str(data.get("model") or self.model), tokens=tokens)

    def generate_stream(self, messages: list[dict], **kw) -> Iterator[dict]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "think": True,
            "options": {"temperature": kw.get("temperature", 0.7),
                        "num_predict": kw.get("max_tokens", 1024)},
        }
        try:
            with self._client() as client:
                with client.stream("POST", "/api/chat", json=payload) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        msg = data.get("message") or {}
                        thinking = msg.get("thinking") or msg.get("reasoning") or ""
                        if thinking:
                            yield {"type": "thinking", "delta": str(thinking)}
                        content = msg.get("content") or ""
                        if content:
                            yield {"type": "text", "delta": str(content)}
                        if data.get("done"):
                            break
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"Ollama 流式调用失败（{self.base_url}）：{exc}。"
                "请确认已运行 `ollama serve`"
            ) from exc

    def health_check(self) -> bool:
        try:
            with self._client() as client:
                resp = client.get("/api/tags", timeout=5.0)
                return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False
