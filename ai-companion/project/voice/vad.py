"""语音活动检测（VAD）：webrtcvad 优先、能量检测兜底的双层实现。

- 顶层零重依赖；webrtcvad 在 VAD 构造时懒加载尝试（SPEC §1）。
- 无 webrtcvad（如树莓派装不上轮子）时自动降级为纯 stdlib 能量检测。
- 帧约定：16kHz / 单声道 / int16，一帧 30ms = 480 采样 = 960 字节
  （webrtcvad 合法帧长 10/20/30ms，本模块统一 30ms）。
"""
from __future__ import annotations

import array
import math

from core.logging_utils import get_logger

logger = get_logger(__name__)

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 480
FRAME_BYTES = FRAME_SAMPLES * 2                 # int16


def frame_rms(frame: bytes) -> float:
    """计算一帧 int16 PCM 的 RMS（纯 stdlib，供能量检测与测试使用）。"""
    if not frame:
        return 0.0
    samples = array.array("h")
    samples.frombytes(frame[: len(frame) - (len(frame) % 2)])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


class EnergyVAD:
    """能量检测兜底实现：RMS 超过阈值视为语音。

    阈值默认 500（int16 量级），安静环境下典型底噪 < 200，正常说话 > 1000；
    可通过 energy_threshold 调整，或用 calibrate() 自适应底噪。
    """

    backend = "energy"

    def __init__(self, energy_threshold: float = 500.0):
        self.energy_threshold = energy_threshold

    def calibrate(self, silent_frames: list[bytes], margin: float = 2.5) -> None:
        """用若干底噪帧自适应阈值。"""
        if not silent_frames:
            return
        noise = max(frame_rms(f) for f in silent_frames)
        self.energy_threshold = max(200.0, noise * margin)
        logger.info("能量 VAD 自适应阈值：%.0f", self.energy_threshold)

    def is_speech(self, frame: bytes, sample_rate: int = SAMPLE_RATE) -> bool:
        return frame_rms(frame) >= self.energy_threshold


class WebRTCVAD:
    """webrtcvad 实现（构造时懒加载 webrtcvad 包）。"""

    backend = "webrtcvad"

    def __init__(self, aggressiveness: int = 2):
        import webrtcvad  # 懒加载（SPEC §1）

        self._vad = webrtcvad.Vad(aggressiveness)

    def is_speech(self, frame: bytes, sample_rate: int = SAMPLE_RATE) -> bool:
        # webrtcvad 只接受 10/20/30ms 帧（int16 字节数 = 采样数×2）；
        # 异常帧长一律交给能量判断兜底
        valid_bytes = {sample_rate * ms // 1000 * 2 for ms in (10, 20, 30)}
        if len(frame) not in valid_bytes:
            return frame_rms(frame) >= 500.0
        try:
            return bool(self._vad.is_speech(frame, sample_rate))
        except Exception:  # 非法帧等异常不向上抛
            return frame_rms(frame) >= 500.0


class VAD:
    """双层 VAD 门面：优先 webrtcvad，缺失时自动降级能量检测。

    构造不崩溃于任何环境：webrtcvad 装不上只记日志并降级。
    """

    def __init__(self, aggressiveness: int = 2, energy_threshold: float = 500.0):
        try:
            self._impl = WebRTCVAD(aggressiveness=aggressiveness)
            logger.info("VAD 使用 webrtcvad（aggressiveness=%d）", aggressiveness)
        except ImportError:
            self._impl = EnergyVAD(energy_threshold=energy_threshold)
            logger.info(
                "webrtcvad 未安装，VAD 降级为能量检测（pip install webrtcvad 可启用）"
            )

    @property
    def backend(self) -> str:
        return self._impl.backend

    def is_speech(self, frame: bytes, sample_rate: int = SAMPLE_RATE) -> bool:
        return self._impl.is_speech(frame, sample_rate)
