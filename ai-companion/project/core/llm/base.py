"""LLM 后端抽象（SPEC §3.4）。

模块顶层只允许轻量 import（abc/dataclass/typing）；网络/推理依赖一律在
具体后端的方法内懒加载。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


@dataclass
class GenerateResult:
    text: str            # 原始输出（可能含 <think>）
    reasoning: str       # 后端原生 reasoning_content，无则 ""
    model: str
    tokens: int


class LLMBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    def generate(self, messages: list[dict], temperature: float = 0.7,
                 max_tokens: int = 1024) -> GenerateResult:
        """同步生成完整回复。"""

    @abstractmethod
    def generate_stream(self, messages: list[dict], **kw) -> Iterator[dict]:
        """流式生成，逐段产出 {"type": "thinking"|"text", "delta": str}。"""

    @abstractmethod
    def health_check(self) -> bool:
        """后端是否可用。"""
