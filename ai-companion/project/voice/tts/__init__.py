"""voice.tts 子包：TTSEngine 抽象 + 工厂。

顶层只做轻量 import；edge-tts / piper 重依赖均在引擎方法内懒加载。
"""
from __future__ import annotations

import os

from voice.tts.base import TTSDependencyError, TTSEngine, TTSError
from voice.tts.clone_engine import CloneTTSEngine
from voice.tts.edge_tts_engine import EdgeTTSEngine
from voice.tts.piper_engine import PiperModelNotFoundError, PiperTTSEngine

__all__ = [
    "TTSEngine",
    "TTSError",
    "TTSDependencyError",
    "PiperModelNotFoundError",
    "EdgeTTSEngine",
    "PiperTTSEngine",
    "CloneTTSEngine",
    "create_tts_engine",
]


def create_tts_engine(settings) -> TTSEngine:
    """按 settings.tts_engine 创建 TTS 引擎（不 import 任何重依赖）。

    settings.tts_engine: "edge_tts"（默认）| "piper"。
    piper 的模型路径取 settings.piper_model_path 或环境变量 HERMES_PIPER_MODEL；
    缺失时不在这里报错，而是推迟到首次 synthesize() 时抛出含安装指引的异常。
    """
    name = (getattr(settings, "tts_engine", "") or "edge_tts").strip().lower()
    if name in ("edge_tts", "edge", "edgetts"):
        return EdgeTTSEngine()
    if name in ("clone", "gpt_sovits", "gpt-sovits", "sovits"):
        return CloneTTSEngine(
            api_base=getattr(settings, "clone_api_base", "") or "http://127.0.0.1:9880",
            ref_audio=getattr(settings, "clone_ref_audio", "") or "",
            ref_text=getattr(settings, "clone_ref_text", "") or "",
        )
    if name == "piper":
        model_path = getattr(settings, "piper_model_path", "") or os.environ.get(
            "HERMES_PIPER_MODEL", ""
        )
        return PiperTTSEngine(model_path=model_path)
    raise ValueError(f"未知 TTS 引擎：{name!r}（可选：edge_tts | piper | clone）")
