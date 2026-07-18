"""faster-whisper 语音识别封装（SPEC §3.7）。

faster-whisper（及其底层 ctranslate2）只在首次 transcribe() 时懒加载，
构造 WhisperSTT 不 import 任何重依赖（SPEC §1 懒加载铁律）。
"""
from __future__ import annotations

from core.logging_utils import get_logger

logger = get_logger(__name__)

INSTALL_HINT = (
    "faster-whisper 未安装。请执行：pip install faster-whisper\n"
    "（纯 CPU 可跑；首次转写会自动下载对应规格的模型，需要一次网络）"
)


class STTError(RuntimeError):
    """语音识别失败的统一异常。"""


class WhisperSTT:
    """faster-whisper 封装。

    :param model_size: 模型规格（tiny/base/small/medium/large-v3 等），
        来自 settings.stt_model_size，默认 "small"。
    :param device: "auto" | "cpu" | "cuda"，默认 auto。
    :param compute_type: "default" | "int8" | "float16" 等，默认 default。
    """

    def __init__(self, model_size: str = "small", device: str = "auto",
                 compute_type: str = "default"):
        self.model_size = model_size or "small"
        self.device = device
        self.compute_type = compute_type
        self._model = None  # WhisperModel，首次 transcribe 时懒加载

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel  # 懒加载（SPEC §1）
        except ImportError as exc:
            raise STTError(INSTALL_HINT) from exc
        logger.info("加载 faster-whisper 模型：%s（device=%s, compute=%s）",
                    self.model_size, self.device, self.compute_type)
        try:
            self._model = WhisperModel(
                self.model_size, device=self.device, compute_type=self.compute_type
            )
        except Exception as exc:
            raise STTError(f"faster-whisper 模型加载失败（{self.model_size}）：{exc}") from exc
        return self._model

    def transcribe(self, audio_path: str) -> str:
        """把音频文件转写为文本；失败抛 STTError（由 pipeline 兜底降级）。"""
        model = self._load()
        try:
            segments, _info = model.transcribe(audio_path)
            text = "".join(seg.text for seg in segments).strip()
        except Exception as exc:
            raise STTError(f"语音转写失败（{audio_path}）：{exc}") from exc
        logger.debug("STT 结果：%s", text)
        return text
