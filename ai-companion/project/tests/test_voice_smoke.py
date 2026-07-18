"""voice 模块纯 mock 冒烟测试。

铁律：无 GPU、无音频设备、无网络环境可跑——
不 import 任何重依赖（torch/faster-whisper/sounddevice/edge-tts/piper/
webrtcvad/openwakeword），不触碰真实硬件与网络。
"""
import array
import math
import sys
import threading
from types import SimpleNamespace

import pytest

# 重依赖清单：整个测试过程中绝不允许出现在 sys.modules
HEAVY_DEPS = [
    "torch", "faster_whisper", "sounddevice", "soundfile",
    "edge_tts", "piper", "webrtcvad", "openwakeword", "numpy",
]


def assert_no_heavy_imports():
    for name in HEAVY_DEPS:
        assert name not in sys.modules, f"重依赖 {name} 不应被 import"


@pytest.fixture(autouse=True)
def _check_heavy_deps():
    assert_no_heavy_imports()
    yield
    assert_no_heavy_imports()


# ---------- 1. 模块可 import（顶层零重依赖） ----------

def test_modules_importable():
    import voice
    import voice.pipeline
    import voice.stt
    import voice.vad
    import voice.wakeword
    import voice.tts
    import voice.tts.base
    import voice.tts.edge_tts_engine
    import voice.tts.piper_engine

    assert voice.VoicePipeline is voice.pipeline.VoicePipeline


# ---------- 2. TTSEngine 抽象可被假实现 ----------

def test_tts_engine_abstract():
    from voice.tts.base import TTSEngine

    with pytest.raises(TypeError):  # 抽象类不可直接实例化
        TTSEngine()


def test_tts_engine_fake_implementation(tmp_path):
    from voice.tts.base import TTSEngine

    class FakeTTS(TTSEngine):
        name = "fake"

        def synthesize(self, text: str, voice: str, out_path: str,
                       style: str = "") -> str:
            assert style == "gentle"  # 签名严格按 §3.7
            with open(out_path, "wb") as f:
                f.write(b"FAKE-AUDIO")
            return out_path

    engine = FakeTTS()
    out = str(tmp_path / "out.wav")
    result = engine.synthesize("主人好", voice="v1", out_path=out, style="gentle")
    assert result == out
    with open(out, "rb") as f:
        assert f.read() == b"FAKE-AUDIO"


# ---------- 3. TTS 工厂（不触发重依赖 import） ----------

def test_create_tts_engine_edge_default():
    from voice.tts import EdgeTTSEngine, create_tts_engine

    engine = create_tts_engine(SimpleNamespace(tts_engine="edge_tts"))
    assert isinstance(engine, EdgeTTSEngine)
    assert engine.output_ext == ".mp3"
    assert "edge_tts" not in sys.modules  # 工厂与构造均为懒加载


def test_create_tts_engine_default_when_missing_attr():
    from voice.tts import EdgeTTSEngine, create_tts_engine

    engine = create_tts_engine(SimpleNamespace())  # 无 tts_engine 字段 → 默认 edge
    assert isinstance(engine, EdgeTTSEngine)


def test_create_tts_engine_piper():
    from voice.tts import PiperTTSEngine, create_tts_engine

    engine = create_tts_engine(
        SimpleNamespace(tts_engine="piper", piper_model_path="/nonexistent/m.onnx")
    )
    assert isinstance(engine, PiperTTSEngine)
    assert "piper" not in sys.modules  # 构造不 import piper 包


def test_create_tts_engine_unknown():
    from voice.tts import create_tts_engine

    with pytest.raises(ValueError, match="未知 TTS 引擎"):
        create_tts_engine(SimpleNamespace(tts_engine="no_such_engine"))


def test_piper_missing_model_raises_with_install_hint(tmp_path):
    from voice.tts.piper_engine import PiperModelNotFoundError, PiperTTSEngine

    engine = PiperTTSEngine(model_path=str(tmp_path / "missing.onnx"))
    with pytest.raises(PiperModelNotFoundError) as exc_info:
        engine.synthesize("主人好", voice="", out_path=str(tmp_path / "o.wav"))
    msg = str(exc_info.value)
    assert "pip install piper-tts" in msg       # 含安装指引
    assert "piper-voices" in msg                 # 含模型下载指引
    assert "piper" not in sys.modules            # 报错发生在 import piper 之前


# ---------- 4. STT 懒加载 ----------

def test_whisper_stt_lazy_construct():
    from voice.stt import WhisperSTT

    stt = WhisperSTT(model_size="tiny")
    assert stt.model_size == "tiny"
    assert stt._model is None
    assert "faster_whisper" not in sys.modules


def test_whisper_stt_transcribe_without_dep_raises_stterror(tmp_path):
    from voice.stt import STTError, WhisperSTT

    if "faster_whisper" in sys.modules:
        pytest.skip("环境已装 faster-whisper，跳过依赖缺失分支")
    stt = WhisperSTT()
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"RIFF")
    with pytest.raises(STTError, match="pip install faster-whisper"):
        stt.transcribe(str(audio))


# ---------- 5. VAD 双层实现 ----------

def _loud_frame(amplitude: int = 10000, samples: int = 480) -> bytes:
    arr = array.array("h", (int(amplitude * math.sin(i / 8.0)) for i in range(samples)))
    return arr.tobytes()


def test_energy_vad_silence_vs_loud():
    from voice.vad import EnergyVAD

    vad = EnergyVAD(energy_threshold=500.0)
    assert vad.is_speech(b"\x00" * 960) is False   # 静音
    assert vad.is_speech(_loud_frame()) is True     # 响亮人声
    assert vad.backend == "energy"


def test_vad_auto_fallback_works():
    from voice.vad import VAD

    vad = VAD()  # 任何环境都必须可构造
    assert vad.backend in ("webrtcvad", "energy")
    # 静音帧两种后端都应判非语音
    assert vad.is_speech(b"\x00" * 960) is False


# ---------- 6. 唤醒词优雅禁用 ----------

def test_wakeword_graceful_disable():
    from voice.wakeword import WakeWordDetector

    det = WakeWordDetector()
    assert "openwakeword" not in sys.modules  # 探测不真正 import
    if not det.available:  # 本环境无 openwakeword：优雅禁用并放行
        assert det.wait_for_wake(timeout=0.2) is True
    # 已置位的 stop_event 下也不应卡死
    stop = threading.Event()
    stop.set()
    assert det.wait_for_wake(stop_event=stop, timeout=0.2) in (True, False)


# ---------- 7. Pipeline 在无任何音频依赖时可实例化、全链路不崩 ----------

def _fake_settings(**overrides):
    base = dict(
        tts_engine="edge_tts", stt_model_size="small",
        active_persona="female_companion", data_dir="data", voice_enabled=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _FakeChatResult:
    def __init__(self, text):
        self.text = text


class _FakeEngine:
    def __init__(self):
        self.chat_calls = []

    def chat(self, text):
        self.chat_calls.append(text)
        return _FakeChatResult(f"收到，{text}")


def test_pipeline_instantiable_without_audio_deps():
    from voice.pipeline import VoicePipeline

    pipe = VoicePipeline(_fake_settings(), _FakeEngine())
    assert pipe.tts is not None          # edge_tts 引擎对象（未 import 包）
    assert pipe.stt.model_size == "small"
    assert pipe.vad.backend in ("webrtcvad", "energy")


def test_pipeline_listen_once_degrades_gracefully():
    from voice.pipeline import VoicePipeline

    if "sounddevice" in sys.modules:
        pytest.skip("环境已装 sounddevice，跳过依赖缺失分支")
    pipe = VoicePipeline(_fake_settings(), _FakeEngine())
    # 无 sounddevice：立即返回 ""，不抛异常、不碰硬件
    assert pipe.listen_once(timeout=0.1) == ""


def test_pipeline_speak_degrades_gracefully(tmp_path, monkeypatch):
    from voice.pipeline import VoicePipeline

    if "edge_tts" in sys.modules:
        pytest.skip("环境已装 edge-tts，跳过依赖缺失分支")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))  # 运行时写入限定在 tmp
    pipe = VoicePipeline(_fake_settings(), _FakeEngine())
    persona = SimpleNamespace(
        voice={"edge_tts_voice": "zh-CN-XiaoyiNeural", "speaking_style": "gentle"}
    )
    # 无 edge-tts/无网络/无播放器：合成失败 → 友好降级，不抛异常
    pipe.speak("主人，你好呀", persona)


def test_pipeline_speak_unknown_engine_no_crash(tmp_path, monkeypatch):
    from voice.pipeline import VoicePipeline

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    pipe = VoicePipeline(_fake_settings(tts_engine="no_such"), _FakeEngine())
    assert pipe.tts is None  # 非法引擎 → 记日志并禁用
    pipe.speak("主人好", None)  # 不抛异常


def test_pipeline_converse_loop_exits_immediately_when_stopped():
    from voice.pipeline import VoicePipeline

    engine = _FakeEngine()
    pipe = VoicePipeline(_fake_settings(), engine)
    stop = threading.Event()
    stop.set()  # 已置位：循环应立即退出，不录音、不 chat
    pipe.converse_loop(stop)
    assert engine.chat_calls == []


def test_pipeline_converse_loop_one_round_with_mocks(monkeypatch, tmp_path):
    """全流程 mock：listen/chat/speak 接线正确，且播报可被 stop_event 终止。"""
    from voice.pipeline import VoicePipeline

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    engine = _FakeEngine()
    pipe = VoicePipeline(_fake_settings(), engine)
    stop = threading.Event()

    spoken = []

    def fake_listen(timeout=10.0):
        return "我很好"

    def fake_speak(text, persona, interruptible, stop_event):
        spoken.append(text)
        stop.set()  # 一轮完整对话后停止，避免死循环
        return False

    monkeypatch.setattr(pipe, "listen_once", fake_listen)
    monkeypatch.setattr(pipe, "_speak", fake_speak)
    pipe.converse_loop(stop)
    assert engine.chat_calls == ["我很好"]
    assert spoken == ["收到，我很好"]
