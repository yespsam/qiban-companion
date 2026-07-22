"""UI 冒烟测试（SPEC §3.10）。

- 使用 fastapi.testclient.TestClient，最小 settings（mock 后端、可选子系统全关）。
- core 尚未合并时整模块 pytest.skip（importorskip），合入后自动生效。
- 运行：pytest tests/test_ui_smoke.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

# core 契约（SPEC §3.1-3.3）；未合并时跳过整模块
pytest.importorskip("core.config", reason="core 模块尚未合并")
pytest.importorskip("core.persona", reason="core 模块尚未合并")
pytest.importorskip("core.memory", reason="core 模块尚未合并")
pytest.importorskip("core.emotion", reason="core 模块尚未合并")
pytest.importorskip("core.engine", reason="core 模块尚未合并")
pytest.importorskip("core.llm", reason="core 模块尚未合并")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from ui.app import create_app  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def workdir(tmp_path, monkeypatch):
    """隔离 cwd：人格/关系身份 YAML 拷入 tmp，settings 持久化落在 tmp，不污染仓库。"""
    cfg_dir = tmp_path / "config"
    shutil.copytree(REPO_ROOT / "config" / "personas", cfg_dir / "personas")
    shutil.copytree(REPO_ROOT / "config" / "relationships", cfg_dir / "relationships")
    shutil.copy(REPO_ROOT / "config" / "voices.yaml", cfg_dir / "voices.yaml")
    (tmp_path / "data").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def settings(workdir):
    from core.config import Settings

    return Settings(
        tier="lite",
        llm_backend="mock",       # mock 后端：无模型环境可跑
        model_id="hermes-lite",
        show_thinking=True,
        master_name="主人",
        active_persona="female_companion",
        voice_enabled=False,
        bluetooth_enabled=False,
        mihome_enabled=False,
        cluster_enabled=False,
        data_dir=str(workdir / "data"),
    )


@pytest.fixture()
def client(settings):
    return TestClient(create_app(settings))


# ---------------------------------------------------------------------- 基础
def test_create_app(settings):
    """create_app(最小 settings) 可建，返回 FastAPI 实例。"""
    app = create_app(settings)
    assert isinstance(app, FastAPI)


def test_index_ok(client):
    """GET / 返回 200 且为单页控制台 HTML。"""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "栖伴" in resp.text


def test_static_assets(client):
    for name in ("app.js", "style.css"):
        resp = client.get(f"/static/{name}")
        assert resp.status_code == 200, name


# ---------------------------------------------------------------------- 人格
def test_personas_list(client):
    """GET /api/personas 包含 female_companion / male_companion。"""
    resp = client.get("/api/personas")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = {p["id"] for p in data}
    assert {"female_companion", "male_companion"} <= ids
    for p in data:
        assert {"id", "display_name", "gender"} <= set(p)


def test_persona_select(client):
    resp = client.post("/api/persona/select", json={"persona_id": "male_companion"})
    assert resp.status_code == 200
    assert resp.json()["active_persona"] == "male_companion"
    resp = client.post("/api/persona/select", json={"persona_id": "no_such_persona"})
    assert resp.status_code == 404


# ------------------------------------------------------------------ 关系身份
def test_relationships_list(client):
    """GET /api/relationships → 4 个身份，含 id/display_name/active，默认 lover 选中。"""
    resp = client.get("/api/relationships")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = {r["id"] for r in data}
    assert ids == {"lover", "friend", "bestie", "elder"}
    for r in data:
        assert {"id", "display_name", "active"} <= set(r)
    active = [r for r in data if r["active"]]
    assert len(active) == 1 and active[0]["id"] == "lover"


def test_relationship_select(client):
    resp = client.post("/api/relationship/select", json={"relationship_id": "bestie"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True and body["active_relationship"] == "bestie"
    assert body["display_name"] == "闺蜜"
    # 选中态经 /api/relationships 透出，且 settings 已热更新并持久化
    data = client.get("/api/relationships").json()
    assert [r["id"] for r in data if r["active"]] == ["bestie"]
    assert client.get("/api/settings").json()["active_relationship"] == "bestie"


def test_relationship_select_rejects_bad_input(client):
    assert client.post("/api/relationship/select", json={}).status_code == 400
    resp = client.post("/api/relationship/select", json={"relationship_id": "ghost"})
    assert resp.status_code == 404


def test_relationship_select_hot_updates_engine(client, settings):
    """切换身份后，引擎下一轮对话的系统提示词即含新身份（热更新）。"""
    captured = {}

    class _SpyBackend:
        name = "spy"

        def generate(self, messages, temperature=0.7, max_tokens=1024):
            captured["system"] = messages[0]["content"]
            from core.llm.base import GenerateResult
            return GenerateResult(text="<think>嗯</think>好的", reasoning="",
                                  model="spy", tokens=1)

        def generate_stream(self, messages, **kw):
            yield {"type": "text", "delta": "好的"}

        def health_check(self):
            return True

    app = create_app(settings)
    assert app.state.hermes.engine is not None
    app.state.hermes.engine.backend = _SpyBackend()
    with TestClient(app) as c:
        c.post("/api/relationship/select", json={"relationship_id": "elder"})
        resp = c.post("/api/chat", json={"text": "今天好累"})
        assert resp.status_code == 200
    assert "长辈" in captured["system"]  # elder.yaml display_name 注入系统提示词


# ---------------------------------------------------------------------- 聊天
def test_chat_mock_backend(client):
    """POST /api/chat（mock 后端）返回含 text / thinking 字段的 JSON。"""
    resp = client.post("/api/chat", json={"text": "你好呀，今天过得怎么样"})
    assert resp.status_code == 200
    data = resp.json()
    assert "text" in data and "thinking" in data
    assert isinstance(data["text"], str) and data["text"]
    assert isinstance(data["thinking"], str)
    assert data.get("persona_id") == "female_companion"
    assert "emotion" in data


def test_chat_empty_rejected(client):
    assert client.post("/api/chat", json={"text": "  "}).status_code == 400


def test_ws_chat_stream(client, settings):
    """WS /ws/chat：thinking/text 帧流式到达，done 帧带完整 result。"""
    app = create_app(settings)
    engine_ok = app.state.hermes.engine is not None
    with TestClient(app) as c:
        with c.websocket_connect("/ws/chat") as ws:
            ws.send_json({"text": "你好"})
            types = []
            final = None
            for _ in range(4000):  # 帧数兜底，防死循环
                frame = ws.receive_json()
                types.append(frame.get("type"))
                if frame.get("type") in ("done", "error"):
                    final = frame
                    break
            assert final is not None, "未收到结束帧"
            if engine_ok:
                assert final["type"] == "done"
                result = final["result"]
                assert result["text"]
                assert "thinking" in result
                assert any(t == "thinking" for t in types) or not result["thinking"]
            else:
                assert final["type"] == "error"


def test_ws_engine_unavailable_error_frame(settings):
    """引擎装配失败时 WS 返回错误帧。"""
    app = create_app(settings)
    app.state.hermes.engine = None
    app.state.hermes.engine_error = "测试注入：引擎离线"
    with TestClient(app) as c:
        with c.websocket_connect("/ws/chat") as ws:
            ws.send_json({"text": "在吗"})
            frame = ws.receive_json()
            assert frame["type"] == "error"
            assert "引擎" in frame["message"]


# ----------------------------------------------------------- 可选子系统降级
def test_optional_subsystems_degraded(client):
    """voice/devices/cluster 全关时：端点在线，返回 enabled=false。"""
    voice = client.get("/api/voice/status").json()
    assert voice["enabled"] is False

    resp = client.post("/api/voice/speak", json={"text": "你好"})
    assert resp.status_code == 200 and resp.json()["enabled"] is False
    resp = client.post("/api/voice/transcribe", content=b"fake audio", headers={"content-type": "audio/webm"})
    assert resp.status_code == 200 and resp.json()["enabled"] is False

    devices = client.get("/api/devices").json()
    assert devices["mihome"]["enabled"] is False
    assert devices["bluetooth"]["enabled"] is False

    resp = client.post("/api/devices/control", json={"did": "x", "action": "on"})
    assert resp.status_code == 200 and resp.json()["enabled"] is False

    cluster = client.get("/api/cluster/nodes").json()
    assert cluster["enabled"] is False and cluster["nodes"] == []


def test_voice_speak_accepts_mobile_cast_overrides(workdir, monkeypatch):
    """手机端对话朗读可单次指定人格、身份和声线，而不被全局默认人格锁住。"""
    from core.config import Settings
    from ui import routes

    settings = Settings(
        tier="lite",
        llm_backend="mock",
        model_id="hermes-lite",
        active_persona="female_companion",
        active_relationship="lover",
        voice_enabled=True,
        data_dir=str(workdir / "data"),
    )
    seen = {}

    class FakeTTSEngine:
        output_ext = ".mp3"
        supports_prosody = True

        def synthesize(self, text, voice, out_path, style="", rate="", pitch=""):
            Path(out_path).write_bytes(b"fake mp3")
            return out_path

    def fake_resolve_cast(persona_id, relationship_id, mood, **kwargs):
        seen.update(
            persona_id=persona_id,
            relationship_id=relationship_id,
            mood=mood,
            archetype=kwargs.get("archetype"),
            gender=kwargs.get("gender"),
        )
        return {"voice": "fake-voice", "style": "warm", "rate": "+0%", "pitch": "+0Hz"}

    monkeypatch.setattr(routes, "_make_tts_engine", lambda _settings: FakeTTSEngine())
    monkeypatch.setattr(routes, "resolve_cast", fake_resolve_cast)

    test_client = TestClient(create_app(settings))
    resp = test_client.post(
        "/api/voice/speak",
        json={
            "text": "你好",
            "persona": "male_companion",
            "relationship": "elder",
            "mood": "happy",
            "archetype": "uncle",
        },
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/mpeg")
    assert seen == {
        "persona_id": "male_companion",
        "relationship_id": "elder",
        "mood": "happy",
        "archetype": "uncle",
        "gender": "male",
    }


def test_voice_resources_and_selection_endpoint(workdir):
    from core.config import Settings

    settings = Settings(
        tier="lite",
        llm_backend="mock",
        model_id="hermes-lite",
        active_persona="female_companion",
        active_relationship="lover",
        voice_enabled=True,
        data_dir=str(workdir / "data"),
    )
    test_client = TestClient(create_app(settings))

    resp = test_client.get("/api/voice/voices?persona=female")
    assert resp.status_code == 200
    body = resp.json()
    ids = [item["id"] for item in body["resources"]]
    assert "default" in ids and "loli" in ids and "yujie" in ids
    assert body["persona"]["id"] == "female_companion"

    resp = test_client.post(
        "/api/voice/select",
        json={"persona": "female", "archetype": "yujie"},
    )
    assert resp.status_code == 200
    assert resp.json()["selected"]["name"] == "御姐音"
    assert test_client.get("/api/settings").json()["active_archetype"] == "yujie"

    bad = test_client.post(
        "/api/voice/select",
        json={"persona": "female", "archetype": "uncle"},
    )
    assert bad.status_code == 400


# ---------------------------------------------------------------------- 设置
def test_settings_roundtrip(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_backend"] == "mock"
    assert body["active_persona"] == "female_companion"

    resp = client.post("/api/settings", json={"master_name": "小主人", "unknown_key": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "master_name" in data["applied"]
    assert "unknown_key" in data["ignored"]
    assert client.get("/api/settings").json()["master_name"] == "小主人"


def test_thinking_toggle(client):
    resp = client.post("/api/thinking/toggle", json={"show": False})
    assert resp.status_code == 200 and resp.json()["show_thinking"] is False
    assert client.get("/api/settings").json()["show_thinking"] is False
    resp = client.post("/api/thinking/toggle", json={"show": True})
    assert resp.json()["show_thinking"] is True


def test_console_state_aggregate(client):
    data = client.get("/api/state").json()
    assert data["persona"]["id"] == "female_companion"
    assert data["show_thinking"] is True
    assert "emotion" in data
