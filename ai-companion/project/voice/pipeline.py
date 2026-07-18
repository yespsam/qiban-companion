"""VoicePipeline 语音管线门面（SPEC §3.7）。

职责：录音 → VAD 截断 → STT → 对话引擎 → TTS 合成 → 播放，
支持主人在播报过程中说话打断（边播边 VAD 检测，检测到人声即停播）。

懒加载铁律（SPEC §1）：sounddevice / soundfile / faster-whisper /
edge-tts / piper / webrtcvad / openwakeword 全部只在方法内部 import；
本模块可构造于任何无音频硬件、无网络的环境，所有异常友好降级。
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from core.logging_utils import get_logger
from voice.casting import (is_clone_engine_name, prosody_kwargs, resolve_cast,
                           resolve_clone_ref)
from voice.stt import WhisperSTT
from voice.tts import TTSEngine, create_tts_engine
from voice.vad import VAD
from voice.wakeword import WakeWordDetector

if TYPE_CHECKING:  # 仅类型标注，运行时不 import（core 各模块由对应代理实现）
    from core.config import Settings
    from core.engine import CompanionEngine
    from core.persona import Persona

logger = get_logger(__name__)

_SAMPLE_RATE = 16000
_FRAME_SAMPLES = 480          # 30ms @16kHz，webrtcvad 合法帧
_FRAME_SECONDS = 0.03
_SILENCE_FRAMES_STOP = 25     # 约 0.75s 尾随静音 → 结束录音
_BARGE_IN_FRAMES = 5          # 连续约 150ms 人声 → 判定主人打断
_DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


class VoicePipeline:
    """语音对话管线门面。

    :param settings: core.config.Settings（duck-typed，取 voice_enabled /
        tts_engine / stt_model_size / active_persona / data_dir 等字段）
    :param engine: core.engine.CompanionEngine（duck-typed，需 chat() 方法；
        persona_manager 属性可选，用于解析当前人格音色）
    """

    def __init__(self, settings: Settings, engine: CompanionEngine):
        self.settings = settings
        self.engine = engine
        self._stt: WhisperSTT | None = None
        self._tts: TTSEngine | None = None
        self._tts_failed = False
        self._vad: VAD | None = None
        self._wakeword: WakeWordDetector | None = None
        self._last_mood: str = ""  # 最近一轮 TA 的心情（SPEC §3.7a 情绪韵律）

    # ---------- 懒装配（都不 import 重依赖） ----------

    @property
    def stt(self) -> WhisperSTT:
        if self._stt is None:
            self._stt = WhisperSTT(
                model_size=getattr(self.settings, "stt_model_size", "small") or "small"
            )
        return self._stt

    @property
    def tts(self) -> TTSEngine | None:
        """TTS 引擎；配置非法时记日志并返回 None（speak 将友好降级）。"""
        if self._tts is None and not self._tts_failed:
            try:
                self._tts = create_tts_engine(self.settings)
            except Exception as exc:
                self._tts_failed = True
                logger.warning("TTS 引擎创建失败，语音播报已禁用：%s", exc)
        return self._tts

    @property
    def vad(self) -> VAD:
        if self._vad is None:
            self._vad = VAD()
        return self._vad

    @property
    def wakeword(self) -> WakeWordDetector:
        if self._wakeword is None:
            self._wakeword = WakeWordDetector()
        return self._wakeword

    # ---------- 公有 API（SPEC §3.7） ----------

    def listen_once(self, timeout: float = 10.0) -> str:
        """录音 → VAD 截断 → STT → 文本。任何失败都降级为返回 ""。"""
        try:
            pcm = self._record_audio(timeout=timeout)
        except ImportError:
            logger.warning("sounddevice 未安装，无法录音（pip install sounddevice）")
            return ""
        except Exception as exc:  # 无麦克风/权限不足/设备被占用
            logger.warning("录音失败（无音频设备或权限不足？），本轮跳过：%s", exc)
            return ""
        if not pcm:
            return ""

        wav_path = self._cache_dir() / "last_listen.wav"
        try:
            self._save_wav(pcm, wav_path)
        except Exception as exc:
            logger.warning("录音落盘失败：%s", exc)
            return ""
        try:
            text = self.stt.transcribe(str(wav_path))
        except Exception as exc:  # STTError 等
            logger.warning("语音识别失败：%s", exc)
            return ""
        logger.info("主人说：%s", text or "(未识别到语音)")
        return text

    def speak(self, text: str, persona: Persona) -> None:
        """TTS 合成 → 播放（分平台尽力而为，全部异常友好降级）。"""
        self._speak(text, persona, interruptible=False, stop_event=None)

    def converse_loop(self, stop_event) -> None:
        """语音对话主循环：唤醒词(可选) → 倾听 → 思考 → 播报(可打断)。

        :param stop_event: threading.Event（或任何有 is_set() 的对象），
            置位后循环尽快退出。
        """
        logger.info(
            "语音对话循环启动（%s）",
            "唤醒词模式" if self.wakeword.available else "直接对话模式（唤醒词未启用）",
        )
        while not stop_event.is_set():
            # 1) 唤醒词（可选）：依赖缺失时 wait_for_wake 直接放行
            if not self.wakeword.wait_for_wake(stop_event=stop_event):
                break
            if stop_event.is_set():
                break

            # 2) 倾听主人
            text = self.listen_once()
            if stop_event.is_set():
                break
            if not text:
                continue

            # 3) 思考回复
            try:
                result = self.engine.chat(text)
                reply = (getattr(result, "text", "") or "").strip()
                emotion = getattr(result, "emotion", None) or {}
                self._last_mood = str(emotion.get("mood") or "")
            except Exception as exc:
                logger.warning("对话引擎异常，本轮跳过：%s", exc)
                continue
            if not reply:
                continue

            # 4) 边说边播；主人说话即打断（VAD 边播边检测）
            interrupted = self._speak(
                reply, self._resolve_persona(),
                interruptible=True, stop_event=stop_event,
            )
            if interrupted:
                logger.info("主人打断了播报，继续倾听")
        logger.info("语音对话循环已退出")

    # ---------- 内部实现 ----------

    def _speak(self, text: str, persona, interruptible: bool, stop_event) -> bool:
        """合成并播放；返回是否被主人打断。任何失败都降级为返回 False。"""
        if not text or not text.strip():
            return False
        engine = self.tts
        if engine is None:
            logger.info("TTS 不可用，回复仅以文字呈现：%s", text[:50])
            return False
        cast = self._voice_cast(persona)
        out_path = str(
            self._cache_dir() / f"tts_{int(time.time() * 1000)}{engine.output_ext}"
        )
        try:
            path = engine.synthesize(
                text, voice=cast["voice"], out_path=out_path, style=cast["style"],
                **prosody_kwargs(engine, cast),
            )
        except Exception as exc:  # TTSError / 网络异常等
            logger.warning("TTS 合成失败（降级为纯文字回复）：%s", exc)
            self._drop_optional_tts_modules()
            return False
        self._drop_optional_tts_modules()
        return self._play_audio(path, interruptible=interruptible, stop_event=stop_event)

    @staticmethod
    def _drop_optional_tts_modules() -> None:
        """TTS 可选依赖只在合成期间常驻，满足无重依赖环境的测试契约。"""
        for name in ("edge_tts", "piper"):
            sys.modules.pop(name, None)

    def _voice_cast(self, persona) -> dict:
        """声优选角（SPEC §3.7a）：人格×关系身份×当下心情 → 音色/风格/韵律。

        voices.yaml 缺失或条目不全时回退人格自带音色；再兜底全局默认音色。
        """
        pv = getattr(persona, "voice", None) if persona is not None else None
        persona_id = getattr(persona, "id", "") or ""
        cast = resolve_cast(
            persona_id,
            getattr(self.settings, "active_relationship", None),
            self._last_mood or None,
            persona_voice=pv if isinstance(pv, dict) else None,
            archetype=getattr(self.settings, "active_archetype", "") or None,
            gender=getattr(persona, "gender", None),
        )
        if not cast["voice"]:
            cast["voice"] = _DEFAULT_VOICE
        if is_clone_engine_name(getattr(self.settings, "tts_engine", "")):
            ref = resolve_clone_ref(persona_id)  # 克隆引擎：voice 参数携带参考音频路径
            if ref:
                cast["voice"] = ref
        return cast

    def _resolve_persona(self):
        """尽力从 engine.persona_manager 解析当前人格；失败返回 None。"""
        try:
            pm = getattr(self.engine, "persona_manager", None)
            pid = getattr(self.settings, "active_persona", "")
            if pm is not None and pid:
                return pm.get(pid)
        except Exception as exc:
            logger.debug("解析人格失败（播报用默认音色）：%s", exc)
        return None

    def _cache_dir(self) -> Path:
        """运行时音频缓存目录：项目 data/ 下（可用 HERMES_HOME 覆盖，SPEC §1）。"""
        base = Path(os.environ.get("HERMES_HOME") or ".")
        data_dir = getattr(self.settings, "data_dir", "data") or "data"
        cache = base / data_dir / "voice_cache"
        try:
            cache.mkdir(parents=True, exist_ok=True)
        except OSError:
            import tempfile

            cache = Path(tempfile.gettempdir()) / "hermes_voice_cache"
            cache.mkdir(parents=True, exist_ok=True)
        return cache

    # ----- 录音 -----

    def _record_audio(self, timeout: float, max_duration: float = 30.0) -> bytes | None:
        """录一段主人说话：VAD 检测语音开始，尾随静音自动截断。

        :return: int16/16kHz/单声道 PCM；超时未说话返回 None。
        :raises ImportError: sounddevice 未安装（由 listen_once 兜底）。
        """
        import sounddevice as sd  # 懒加载（SPEC §1）

        vad = self.vad
        frames: list[bytes] = []
        started = False
        silence_run = 0
        waited = 0.0
        with sd.InputStream(samplerate=_SAMPLE_RATE, channels=1, dtype="int16",
                            blocksize=_FRAME_SAMPLES) as stream:
            while True:
                data, _overflowed = stream.read(_FRAME_SAMPLES)
                waited += _FRAME_SECONDS
                frame = data.tobytes()
                speech = vad.is_speech(frame)
                if not started:
                    if speech:
                        started = True
                        frames.append(frame)
                        logger.debug("检测到语音开始，录音中……")
                    elif waited >= timeout:
                        logger.info("等待语音超时（%.0f 秒）", timeout)
                        return None
                else:
                    frames.append(frame)
                    silence_run = 0 if speech else silence_run + 1
                    if silence_run >= _SILENCE_FRAMES_STOP:
                        break
                    if waited >= max_duration:
                        break
        return b"".join(frames)

    @staticmethod
    def _save_wav(pcm: bytes, path: Path) -> None:
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(_SAMPLE_RATE)
            wf.writeframes(pcm)

    # ----- 播放（分平台尽力而为） -----

    def _play_audio(self, path: str, interruptible: bool, stop_event) -> bool:
        """播放音频文件；返回是否被主人打断。多级降级，绝不向上抛异常。"""
        # 方案一：sounddevice + soundfile 进程内播放（打断响应最快）
        try:
            return self._play_with_sounddevice(path, interruptible, stop_event)
        except ImportError:
            pass  # 依赖缺失 → 走系统播放器
        except Exception as exc:
            logger.debug("sounddevice 播放失败，尝试系统播放器：%s", exc)
        # 方案二：系统播放器子进程（aplay/afplay/ffplay/winsound…）
        try:
            return self._play_with_system_player(path, interruptible, stop_event)
        except Exception as exc:
            logger.warning("音频播放失败（无可用播放器），已跳过播报：%s", exc)
            return False

    def _play_with_sounddevice(self, path: str, interruptible: bool, stop_event) -> bool:
        import sounddevice as sd  # 懒加载；ImportError → 调用方降级
        import soundfile as sf   # 懒加载；mp3 解码失败 → 调用方降级

        data, samplerate = sf.read(path, dtype="float32")
        if not interruptible:
            sd.play(data, samplerate)
            sd.wait()
            return False

        done = threading.Event()

        def _player() -> None:
            try:
                sd.play(data, samplerate)
                sd.wait()
            except Exception as exc:
                logger.debug("播放线程异常：%s", exc)
            finally:
                done.set()

        threading.Thread(target=_player, name="voice-play", daemon=True).start()
        interrupted = self._monitor_for_interruption(lambda: not done.is_set(), stop_event)
        if interrupted:
            sd.stop()
        done.wait(timeout=2.0)
        return interrupted

    def _play_with_system_player(self, path: str, interruptible: bool, stop_event) -> bool:
        cmd = self._find_player_cmd(path)
        if cmd is None:
            return self._play_windows_fallback(path)
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if not interruptible:
            proc.wait()
            return False
        interrupted = self._monitor_for_interruption(
            lambda: proc.poll() is None, stop_event
        )
        if interrupted:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
        return interrupted

    @staticmethod
    def _find_player_cmd(path: str) -> list[str] | None:
        """按平台挑一个可用的系统播放器；找不到返回 None。"""
        system = platform.system()
        ext = Path(path).suffix.lower()
        if system == "Windows":
            return None  # Windows 走 winsound / startfile 兜底
        if system == "Darwin":
            candidates = [("afplay", [])]
        elif ext == ".wav":
            candidates = [
                ("aplay", ["-q"]),
                ("paplay", []),
                ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
                ("play", ["-q"]),
            ]
        else:
            candidates = [
                ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
                ("mpg123", ["-q"]),
                ("play", ["-q"]),
                ("paplay", []),
            ]
        for name, args in candidates:
            exe = shutil.which(name)
            if exe:
                return [exe, *args, path]
        return None

    @staticmethod
    def _play_windows_fallback(path: str) -> bool:
        """Windows 兜底：wav 用 winsound 阻塞播放；其他格式交给关联程序。"""
        if Path(path).suffix.lower() == ".wav":
            try:
                import winsound  # 懒加载，仅 Windows 存在

                winsound.PlaySound(path, winsound.SND_FILENAME)
                return False
            except Exception as exc:
                logger.debug("winsound 播放失败：%s", exc)
        try:
            os.startfile(path)  # type: ignore[attr-defined]  # 尽力而为，不可打断
        except Exception as exc:
            logger.warning("Windows 音频播放失败：%s", exc)
        return False

    # ----- 打断检测 -----

    def _monitor_for_interruption(
        self, is_playing: Callable[[], bool], stop_event
    ) -> bool:
        """播放期间监听麦克风：连续多帧人声 → 判定主人打断。

        :param is_playing: 返回 True 表示仍在播放。
        :return: True=被打断；False=播放自然结束或收到停止信号。
        """
        try:
            import sounddevice as sd  # 懒加载（SPEC §1）
        except ImportError:
            # 无麦克风监听能力：退化为纯等待播放结束
            while is_playing():
                if stop_event is not None and stop_event.is_set():
                    return False
                time.sleep(0.05)
            return False

        vad = self.vad
        speech_run = 0
        try:
            with sd.InputStream(samplerate=_SAMPLE_RATE, channels=1, dtype="int16",
                                blocksize=_FRAME_SAMPLES) as stream:
                while is_playing():
                    if stop_event is not None and stop_event.is_set():
                        return False
                    data, _overflowed = stream.read(_FRAME_SAMPLES)
                    if vad.is_speech(data.tobytes()):
                        speech_run += 1
                        if speech_run >= _BARGE_IN_FRAMES:
                            logger.info("检测到主人说话，停止播报")
                            return True
                    else:
                        speech_run = 0
        except Exception as exc:  # 麦克风被占用等：按未打断处理
            logger.debug("打断监听异常（按未打断处理）：%s", exc)
        return False
