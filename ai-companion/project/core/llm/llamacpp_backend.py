"""llama.cpp 后端（SPEC §3.4）。

优先连接本地 llama-server（OpenAI 兼容 /v1/chat/completions），地址从
config/models.yaml 的 server_url 读取（缺省 http://127.0.0.1:8080）；
server 未运行时尝试以 llama-cpp-python 进程内加载（懒加载），两者皆不可用时
抛出带清晰指引的 RuntimeError。
"""
from __future__ import annotations

import json
import os
from typing import Iterator

import yaml

from core.llm.base import GenerateResult, LLMBackend
from core.logging_utils import get_logger

log = get_logger(__name__)

_DEFAULT_SERVER_URL = "http://127.0.0.1:8080"


class LlamaCppBackend(LLMBackend):
    name = "llamacpp"

    def __init__(self, settings=None, server_url: str | None = None):
        self.model_id = getattr(settings, "model_id", "") if settings else ""
        self.data_dir = getattr(settings, "data_dir", "data") if settings else "data"
        cfg = self._load_model_cfg()
        self.ctx = int(cfg.get("ctx") or 4096)
        self.server_url = (server_url or cfg.get("server_url")
                           or _DEFAULT_SERVER_URL).rstrip("/")
        self.model_path = self._resolve_model_path(cfg)
        self._llama = None  # llama_cpp.Llama 实例，懒加载

    def _load_model_cfg(self) -> dict:
        try:
            with open("config/models.yaml", "r", encoding="utf-8") as f:
                registry = yaml.safe_load(f) or {}
            return (registry.get("models") or {}).get(self.model_id) or {}
        except Exception:  # noqa: BLE001
            return {}

    def _resolve_model_path(self, cfg: dict) -> str:
        if cfg.get("path"):
            return str(cfg["path"])
        fname = str(cfg.get("file") or "")
        candidates = [
            os.path.join(self.data_dir, "models", fname),
            os.path.join("models", fname),
            fname,
        ]
        for path in candidates:
            if path and os.path.exists(path):
                return path
        return candidates[0]  # 不存在时也返回预期路径，便于报错信息指引

    # ---------------- llama-server（OpenAI 兼容 HTTP） ----------------

    def _server_alive(self) -> bool:
        try:
            import httpx  # 懒加载

            with httpx.Client(base_url=self.server_url, timeout=3.0) as client:
                return client.get("/v1/models").status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def _generate_http(self, messages, temperature, max_tokens) -> GenerateResult:
        import httpx  # 懒加载

        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        with httpx.Client(base_url=self.server_url, timeout=600.0) as client:
            resp = client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        reasoning = str(msg.get("reasoning_content") or "")
        text = str(msg.get("content") or "")
        tokens = int((data.get("usage") or {}).get("total_tokens") or 0)
        return GenerateResult(text=text, reasoning=reasoning,
                              model=self.model_id or "llamacpp", tokens=tokens)

    def _generate_stream_http(self, messages, **kw) -> Iterator[dict]:
        import httpx  # 懒加载

        payload = {
            "messages": messages,
            "temperature": kw.get("temperature", 0.7),
            "max_tokens": kw.get("max_tokens", 1024),
            "stream": True,
        }
        with httpx.Client(base_url=self.server_url, timeout=600.0) as client:
            with client.stream("POST", "/v1/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = (data.get("choices") or [{}])[0].get("delta") or {}
                    thinking = delta.get("reasoning_content") or ""
                    if thinking:
                        yield {"type": "thinking", "delta": str(thinking)}
                    content = delta.get("content") or ""
                    if content:
                        yield {"type": "text", "delta": str(content)}

    # ---------------- llama-cpp-python 进程内加载 ----------------

    def _load_local(self):
        if self._llama is None:
            try:
                from llama_cpp import Llama  # 懒加载
            except ImportError as exc:
                raise RuntimeError(
                    "未检测到 llama-server，且 llama-cpp-python 未安装。"
                    "请二选一：1) 启动 llama-server；2) pip install llama-cpp-python"
                ) from exc
            if not os.path.exists(self.model_path):
                raise RuntimeError(
                    f"模型文件不存在: {self.model_path}。"
                    "请先运行 installer/download_model.py 下载对应档位模型"
                )
            self._llama = Llama(model_path=self.model_path, n_ctx=self.ctx, verbose=False)
        return self._llama

    def _generate_local(self, messages, temperature, max_tokens) -> GenerateResult:
        llama = self._load_local()
        out = llama.create_chat_completion(
            messages=messages, temperature=temperature, max_tokens=max_tokens,
        )
        choice = (out.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        reasoning = str(msg.get("reasoning_content") or "")
        text = str(msg.get("content") or "")
        tokens = int((out.get("usage") or {}).get("total_tokens") or 0)
        return GenerateResult(text=text, reasoning=reasoning,
                              model=self.model_id or "llamacpp-local", tokens=tokens)

    # ---------------- LLMBackend 接口 ----------------

    def generate(self, messages: list[dict], temperature: float = 0.7,
                 max_tokens: int = 1024) -> GenerateResult:
        if self._server_alive():
            return self._generate_http(messages, temperature, max_tokens)
        log.info("llama-server 不可用（%s），尝试进程内加载", self.server_url)
        return self._generate_local(messages, temperature, max_tokens)

    def generate_stream(self, messages: list[dict], **kw) -> Iterator[dict]:
        if self._server_alive():
            yield from self._generate_stream_http(messages, **kw)
            return
        # 进程内模式无可靠流式，退化为一次性产出
        result = self._generate_local(
            messages, kw.get("temperature", 0.7), kw.get("max_tokens", 1024))
        if result.reasoning:
            yield {"type": "thinking", "delta": result.reasoning}
        if result.text:
            yield {"type": "text", "delta": result.text}

    def health_check(self) -> bool:
        if self._server_alive():
            return True
        try:
            import llama_cpp  # noqa: F401 懒加载探测

            return os.path.exists(self.model_path)
        except Exception:  # noqa: BLE001
            return False
