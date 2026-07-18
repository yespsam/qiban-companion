"""openwakeword 唤醒词封装（可选功能）。

- openwakeword / numpy / sounddevice 全部懒加载（SPEC §1）。
- 依赖缺失时优雅禁用：available=False、wait_for_wake() 直接放行，
  并给出一键安装提示，绝不影响语音对话主流程。
"""
from __future__ import annotations

import importlib.util
import time

from core.logging_utils import get_logger

logger = get_logger(__name__)

INSTALL_HINT = (
    "唤醒词功能未启用：openwakeword 未安装。"
    "需要「叫名字唤醒」体验可执行：pip install openwakeword\n"
    "（当前为按键/直接对话模式，不影响正常语音聊天）"
)

#: openwakeword 输入帧约定：16kHz / 单声道 / int16 / 80ms = 1280 采样
_FRAME_SAMPLES = 1280


class WakeWordDetector:
    """唤醒词检测器。

    :param model_paths: 自定义唤醒词模型路径列表；空则用 openwakeword 内置模型。
    :param threshold: 唤醒置信度阈值（0-1），默认 0.5。
    """

    def __init__(self, model_paths: list[str] | None = None, threshold: float = 0.5):
        self.model_paths = model_paths or []
        self.threshold = threshold
        self._model = None
        self._hint_shown = False

    @property
    def available(self) -> bool:
        """openwakeword 是否可 import（不真正加载，轻量探测）。"""
        return importlib.util.find_spec("openwakeword") is not None

    def _show_hint_once(self) -> None:
        if not self._hint_shown:
            self._hint_shown = True
            logger.info(INSTALL_HINT)

    def _ensure_model(self):
        """懒加载模型；失败返回 None（调用方据此优雅放行）。"""
        if self._model is not None:
            return self._model
        try:
            from openwakeword.model import Model  # 懒加载（SPEC §1）
        except ImportError:
            self._show_hint_once()
            return None
        try:
            if self.model_paths:
                self._model = Model(wakeword_models=self.model_paths)
            else:
                self._model = Model()
        except Exception as exc:
            logger.warning("唤醒词模型加载失败，已禁用唤醒词：%s", exc)
            return None
        logger.info("唤醒词模型已加载（threshold=%.2f）", self.threshold)
        return self._model

    def detect(self, frame: bytes) -> bool:
        """检测一帧 80ms/16kHz/int16 音频是否命中唤醒词。"""
        model = self._ensure_model()
        if model is None:
            return False
        try:
            import numpy as np  # 懒加载（SPEC §1）

            audio = np.frombuffer(frame, dtype=np.int16)
            prediction = model.predict(audio)
            return any(score >= self.threshold for score in prediction.values())
        except Exception as exc:
            logger.debug("唤醒词检测帧异常（已忽略）：%s", exc)
            return False

    def wait_for_wake(self, stop_event=None, timeout: float | None = None) -> bool:
        """阻塞等待唤醒词。

        :return: True=被唤醒（或唤醒词不可用直接放行）；False=stop_event 触发或超时。
        """
        if not self.available:
            self._show_hint_once()
            return True  # 优雅禁用：无唤醒词直接进入对话
        if self._ensure_model() is None:
            return True
        try:
            import sounddevice as sd  # 懒加载（SPEC §1）
        except ImportError:
            logger.warning("sounddevice 未安装，无法监听唤醒词，直接放行")
            return True

        start = time.monotonic()
        logger.info("等待唤醒词……")
        try:
            with sd.InputStream(samplerate=16000, channels=1, dtype="int16",
                                blocksize=_FRAME_SAMPLES) as stream:
                while True:
                    if stop_event is not None and stop_event.is_set():
                        return False
                    if timeout is not None and time.monotonic() - start >= timeout:
                        return False
                    data, _overflowed = stream.read(_FRAME_SAMPLES)
                    if self.detect(data.tobytes()):
                        logger.info("检测到唤醒词")
                        return True
        except Exception as exc:
            # 麦克风被占用/无音频设备等：唤醒词放行，不让主流程卡死
            logger.warning("唤醒词监听异常（直接放行进入对话）：%s", exc)
            return True
