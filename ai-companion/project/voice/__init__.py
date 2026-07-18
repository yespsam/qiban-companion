"""voice 包：语音对话管线（STT / TTS / VAD / 唤醒词）。

顶层只做轻量 import（SPEC §1 懒加载铁律）；
无 GPU、无音频设备、无网络的环境也能 import 本包。
"""
from voice.pipeline import VoicePipeline

__all__ = ["VoicePipeline"]
