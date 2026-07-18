"""piper 本地离线 TTS 引擎。

piper 包与模型都只在 synthesize() 首次调用时懒加载/校验（SPEC §1）。
模型路径缺失时抛出带安装指引的清晰异常（SPEC §3.7）。
"""
from __future__ import annotations

import os
from pathlib import Path

from core.logging_utils import get_logger
from voice.tts.base import TTSDependencyError, TTSEngine, TTSError

logger = get_logger(__name__)

INSTALL_HINT = """\
piper 离线 TTS 不可用，请按以下步骤安装：
1. 安装 Python 包：pip install piper-tts
2. 下载语音模型（.onnx + .onnx.json）：
   https://huggingface.co/rhasspy/piper-voices （中文推荐 zh_CN-huayan-medium）
3. 配置模型路径（三选一）：
   - config/settings.yaml 增加 piper_model_path: /path/to/zh_CN-huayan-medium.onnx
   - 环境变量 HERMES_PIPER_MODEL=/path/to/model.onnx
   - synthesize() 的 voice 参数直接传入 .onnx 模型路径
"""


class PiperModelNotFoundError(TTSError):
    """piper 模型路径缺失/不存在，异常信息含安装指引。"""


class PiperTTSEngine(TTSEngine):
    """piper 本地离线 TTS（树莓派/无网环境可用）。"""

    name = "piper"
    output_ext = ".wav"

    def __init__(self, model_path: str = "", config_path: str = ""):
        # 轻量构造：只记录路径，不 import piper、不读模型文件。
        self.model_path = model_path or os.environ.get("HERMES_PIPER_MODEL", "")
        self.config_path = config_path
        self._voice = None  # PiperVoice 实例，首次合成时懒加载

    def _resolve_model_path(self, voice: str) -> Path:
        # synthesize 的 voice 参数可直接传 .onnx 路径，优先于构造配置
        candidate = (voice or "").strip()
        if candidate.endswith(".onnx"):
            path = Path(candidate)
        else:
            path = Path(self.model_path) if self.model_path else None
        if path is None or not path.exists():
            raise PiperModelNotFoundError(
                f"piper 模型文件不存在：{path or '(未配置)'}\n{INSTALL_HINT}"
            )
        return path

    def _load_voice(self, model_path: Path):
        if self._voice is not None:
            return self._voice
        try:
            from piper import PiperVoice  # 懒加载（SPEC §1）
        except ImportError as exc:
            raise TTSDependencyError(INSTALL_HINT) from exc
        cfg = self.config_path or str(model_path) + ".json"
        try:
            self._voice = PiperVoice.load(
                str(model_path), config_path=cfg if Path(cfg).exists() else None
            )
        except Exception as exc:
            raise TTSError(f"piper 模型加载失败：{model_path}：{exc}") from exc
        return self._voice

    def synthesize(self, text: str, voice: str, out_path: str, style: str = "") -> str:
        if not text or not text.strip():
            raise TTSError("piper 收到空文本，无法合成")
        if style:
            logger.debug("piper 暂不支持 style=%r，已忽略", style)
        model_path = self._resolve_model_path(voice)
        piper_voice = self._load_voice(model_path)
        import wave  # stdlib，放这里保持顶层最小

        try:
            with wave.open(out_path, "wb") as wav_file:
                piper_voice.synthesize(text, wav_file)
        except Exception as exc:
            raise TTSError(f"piper 合成失败：{exc}") from exc
        return out_path
