"""edge-tts 引擎（默认，在线，高质量，免 GPU）。

edge-tts 为异步 API，这里封装成 §3.7 要求的同步 synthesize()。
edge_tts 包只在 synthesize() 首次调用时懒加载（SPEC §1 懒加载铁律）。
"""
from __future__ import annotations

import asyncio
import re
import threading

from core.logging_utils import get_logger
from voice.tts.base import TTSDependencyError, TTSEngine, TTSError

logger = get_logger(__name__)

INSTALL_HINT = (
    "edge-tts 未安装。请执行：pip install edge-tts\n"
    "（edge-tts 为在线服务，合成时需要网络；离线环境请改用 piper："
    "settings.yaml 中 tts_engine: piper）"
)


_RATE_RE = re.compile(r"^[+-]\d+%$")
_PITCH_RE = re.compile(r"^[+-]\d+Hz$")


def _valid_rate(rate: str) -> bool:
    return bool(rate) and bool(_RATE_RE.match(rate))


def _valid_pitch(pitch: str) -> bool:
    return bool(pitch) and bool(_PITCH_RE.match(pitch))


def _run_coro_sync(coro):
    """同步执行协程；若当前线程已有运行中的事件循环，则放到新线程里跑。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict = {}

    def _runner() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - 需要透传回原线程
            box["error"] = exc

    t = threading.Thread(target=_runner, name="edge-tts-sync", daemon=True)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


class EdgeTTSEngine(TTSEngine):
    """基于 edge-tts 的在线 TTS（默认引擎）。"""

    name = "edge_tts"
    output_ext = ".mp3"
    supports_prosody = True
    DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

    def synthesize(self, text: str, voice: str, out_path: str, style: str = "",
                   rate: str = "", pitch: str = "") -> str:
        if not text or not text.strip():
            raise TTSError("edge-tts 收到空文本，无法合成")
        voice = (voice or "").strip() or self.DEFAULT_VOICE
        if style:
            # edge-tts Communicate 不直接支持 style，保留参数以符合接口契约。
            logger.debug("edge-tts 暂不支持 style=%r，已忽略", style)
        _run_coro_sync(self._synthesize_async(text, voice, out_path, rate, pitch))
        return out_path

    async def _synthesize_async(self, text: str, voice: str, out_path: str,
                                rate: str = "", pitch: str = "") -> None:
        try:
            import edge_tts  # 懒加载（SPEC §1）
        except ImportError as exc:
            raise TTSDependencyError(INSTALL_HINT) from exc
        kwargs: dict = {}
        if _valid_rate(rate):
            kwargs["rate"] = rate
        elif rate:
            logger.debug("忽略非法 rate=%r（应如 '+8%%' / '-12%%'）", rate)
        if _valid_pitch(pitch):
            kwargs["pitch"] = pitch
        elif pitch:
            logger.debug("忽略非法 pitch=%r（应如 '+2Hz' / '-2Hz'）", pitch)
        try:
            communicate = edge_tts.Communicate(text, voice=voice, **kwargs)
            await communicate.save(out_path)
        except TTSError:
            raise
        except Exception as exc:  # 网络/服务异常统一包装
            raise TTSError(f"edge-tts 合成失败（voice={voice}）：{exc}") from exc
