"""克隆声优测试（SPEC §3.7a）：CloneTTSEngine + /api/voice/upload。

铁律同 test_voice_smoke：不 import 真实重依赖（httpx 用桩注入），不触网不触硬件。
"""
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("core.config", reason="core 模块尚未合并")

from fastapi.testclient import TestClient  # noqa: E402

from ui.app import create_app  # noqa: E402
from voice.tts import CloneTTSEngine, create_tts_engine
from voice.tts.base import TTSError

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------- 1. 工厂 ----------

def test_factory_clone():
    engine = create_tts_engine(SimpleNamespace(
        tts_engine="clone",
        clone_api_base="http://127.0.0.1:9880",
        clone_ref_audio="/tmp/ref.wav",
        clone_ref_text="主人好",
    ))
    assert isinstance(engine, CloneTTSEngine)
    assert engine.ref_audio == "/tmp/ref.wav"
    assert engine.output_ext == ".wav"


def test_factory_gpt_sovits_alias():
    engine = create_tts_engine(SimpleNamespace(tts_engine="gpt_sovits"))
    assert isinstance(engine, CloneTTSEngine)


# ---------- 2. 合成行为 ----------

def test_clone_no_ref_raises_with_upload_hint(tmp_path):
    engine = CloneTTSEngine(ref_audio="")
    with pytest.raises(TTSError, match="upload"):
        engine.synthesize("主人好", voice="", out_path=str(tmp_path / "o.wav"))


def test_clone_synthesize_with_fake_httpx(tmp_path, monkeypatch):
    calls = []

    class _Resp:
        content = b"RIFF-fake-wav"
        def raise_for_status(self): pass

    fake_httpx = SimpleNamespace(
        get=lambda url, params=None, timeout=None: calls.append((url, params)) or _Resp()
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)

    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"RIFF")
    engine = CloneTTSEngine(api_base="http://127.0.0.1:9880/", ref_audio=str(ref))
    out = str(tmp_path / "out.wav")
    assert engine.synthesize("主人，吃饭了吗", voice="", out_path=out) == out
    assert Path(out).read_bytes() == b"RIFF-fake-wav"
    url, params = calls[0]
    assert url == "http://127.0.0.1:9880/tts"  # 尾部斜杠已规整
    assert params["text"] == "主人，吃饭了吗"
    assert params["ref_audio_path"] == str(ref)


def test_clone_voice_param_overrides_ref(tmp_path, monkeypatch):
    """synthesize 的 voice 参数若是存在的音频路径，则当成本轮参考音频（按人格切声优）。"""
    calls = []
    fake_httpx = SimpleNamespace(
        get=lambda url, params=None, timeout=None: calls.append(params)
        or SimpleNamespace(content=b"x", raise_for_status=lambda: None)
    )
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    override = tmp_path / "persona_ref.wav"
    override.write_bytes(b"RIFF")
    engine = CloneTTSEngine(ref_audio="/nonexistent/default.wav")
    engine.synthesize("你好", voice=str(override), out_path=str(tmp_path / "o.wav"))
    assert calls[0]["ref_audio_path"] == str(override)


def test_clone_service_down_wraps_error(tmp_path, monkeypatch):
    def _boom(url, params=None, timeout=None):
        raise ConnectionError("refused")
    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(get=_boom))
    ref = tmp_path / "ref.wav"; ref.write_bytes(b"RIFF")
    engine = CloneTTSEngine(ref_audio=str(ref))
    with pytest.raises(TTSError, match="api.py"):
        engine.synthesize("你好", voice="", out_path=str(tmp_path / "o.wav"))


# ---------- 3. 上传端点 ----------

@pytest.fixture()
def workdir(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config" / "personas", cfg_dir / "personas")
    shutil.copytree(REPO_ROOT / "config" / "relationships", cfg_dir / "relationships")
    shutil.copy(REPO_ROOT / "config" / "voices.yaml", cfg_dir / "voices.yaml")
    (tmp_path / "data").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def client(workdir):
    from core.config import Settings

    settings = Settings(
        tier="lite", llm_backend="mock", model_id="hermes-lite",
        active_persona="female_companion", voice_enabled=True,
        bluetooth_enabled=False, mihome_enabled=False, cluster_enabled=False,
        data_dir=str(workdir / "data"),
    )
    return TestClient(create_app(settings))


AUDIO = b"RIFF" + b"\x00" * 2000  # 假音频字节


def test_upload_default_target(client, workdir):
    r = client.post("/api/voice/upload?target=default",
                    content=AUDIO, headers={"content-type": "audio/wav"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["target"] == "default"
    saved = Path(body["path"])
    assert saved.exists() and saved.read_bytes() == AUDIO
    assert body["settings_saved"] is True
    # settings.yaml 已持久化 clone_ref_audio
    import yaml
    persisted = yaml.safe_load((workdir / "config" / "settings.yaml").read_text(encoding="utf-8"))
    assert persisted["clone_ref_audio"] == str(saved)


def test_upload_persona_target_writes_voices_yaml(client, workdir):
    r = client.post("/api/voice/upload?target=female_companion",
                    content=AUDIO, headers={"content-type": "audio/mpeg"})
    body = r.json()
    assert body["ok"] is True
    assert body["path"].endswith("female_companion_ref.mp3")
    assert body["voices_yaml_updated"] is True
    import yaml
    data = yaml.safe_load((workdir / "config" / "voices.yaml").read_text(encoding="utf-8"))
    assert data["clone"]["voices"]["female_companion"]["ref_audio"] == body["path"]
    # casting 能解析到该参考音频
    from voice.casting import resolve_clone_ref
    assert resolve_clone_ref("female_companion") == body["path"]


def test_upload_rejects_bad_target(client):
    r = client.post("/api/voice/upload?target=hacker",
                    content=AUDIO, headers={"content-type": "audio/wav"})
    assert r.status_code == 400


def test_upload_rejects_empty(client):
    r = client.post("/api/voice/upload", content=b"", headers={"content-type": "audio/wav"})
    assert r.status_code == 400


def test_no_heavy_imports():
    for name in ("torch", "edge_tts", "piper", "sounddevice"):
        assert name not in sys.modules
