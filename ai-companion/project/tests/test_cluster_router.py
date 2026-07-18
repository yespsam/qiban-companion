"""cluster 模块单元测试（SPEC §6）。

覆盖：注册/心跳/ttl 过期、deregister、注册表持久化与原子写入、
least_load / local_first 两种选点策略、全灭时抛 ClusterUnavailable、
route_chat 的 HTTP 调用（一律 mock，不发起真实网络请求）。

运行环境要求：无 GPU、无模型、无网络（httpx.post 全部 monkeypatch）。
"""
from __future__ import annotations

import json
import time

import httpx
import pytest

from cluster import (
    ClusterRouter,
    ClusterUnavailable,
    NodeInfo,
    NodeRegistry,
)

MODEL = "hermes-3-8b"


def _node(
    node_id: str,
    host: str = "10.0.0.1",
    port: int = 8080,
    models=(MODEL,),
    load: float = 0.1,
    age: float = 0.0,
    role: str = "worker",
) -> NodeInfo:
    """构造测试节点；age 表示心跳距今秒数（用于模拟超时）。"""
    return NodeInfo(
        node_id=node_id,
        role=role,
        host=host,
        port=port,
        models=list(models),
        gpu_vram_mb=8192,
        load=load,
        last_heartbeat=time.time() - age,
    )


@pytest.fixture()
def registry(tmp_path):
    return NodeRegistry(str(tmp_path / "cluster_nodes.json"))


@pytest.fixture()
def router(registry):
    # local_ids 显式注入，保证 local_first 测试与运行机器无关
    return ClusterRouter(registry, ttl=30.0, timeout=5.0, local_ids={"127.0.0.1", "localhost"})


# ---------------------------------------------------------------------------
# NodeRegistry：注册 / 心跳 / ttl 过期 / 摘除 / 持久化
# ---------------------------------------------------------------------------

class TestNodeRegistry:
    def test_register_and_alive(self, registry):
        registry.register(_node("n1"))
        alive = registry.alive(ttl=30.0)
        assert [n.node_id for n in alive] == ["n1"]

    def test_register_without_heartbeat_sets_now(self, registry):
        info = _node("n1")
        info.last_heartbeat = 0.0
        registry.register(info)
        assert registry.alive(ttl=30.0)[0].last_heartbeat > 0

    def test_ttl_expiry_filters_dead_nodes(self, registry):
        registry.register(_node("fresh"))
        registry.register(_node("stale", age=120.0))  # 心跳在 120s 前
        alive_ids = [n.node_id for n in registry.alive(ttl=30.0)]
        assert alive_ids == ["fresh"]
        # 放宽 ttl 后超时节点重新出现
        assert {n.node_id for n in registry.alive(ttl=300.0)} == {"fresh", "stale"}

    def test_heartbeat_revives_expired_node(self, registry):
        registry.register(_node("n1", age=120.0))
        assert registry.alive(ttl=30.0) == []
        registry.heartbeat("n1")
        assert [n.node_id for n in registry.alive(ttl=30.0)] == ["n1"]

    def test_heartbeat_unknown_node_is_ignored(self, registry):
        registry.heartbeat("ghost")  # 不抛异常
        assert registry.alive() == []

    def test_deregister(self, registry):
        registry.register(_node("n1"))
        registry.register(_node("n2", host="10.0.0.2"))
        registry.deregister("n1")
        registry.deregister("n1")  # 重复摘除静默忽略
        assert [n.node_id for n in registry.alive()] == ["n2"]

    def test_persistence_roundtrip(self, tmp_path):
        path = str(tmp_path / "cluster_nodes.json")
        reg1 = NodeRegistry(path)
        reg1.register(_node("n1", host="10.0.0.7", port=9090, models=[MODEL, "hermes-lite"], load=0.42))
        reg2 = NodeRegistry(path)  # 新实例从同一文件恢复
        nodes = reg2.alive(ttl=30.0)
        assert len(nodes) == 1
        n = nodes[0]
        assert n.node_id == "n1" and n.host == "10.0.0.7" and n.port == 9090
        assert n.models == [MODEL, "hermes-lite"] and n.load == pytest.approx(0.42)

    def test_atomic_write_leaves_no_tmp_files(self, registry, tmp_path):
        registry.register(_node("n1"))
        registry.register(_node("n2", host="10.0.0.2"))
        files = [p.name for p in tmp_path.iterdir()]
        assert files == ["cluster_nodes.json"]
        data = json.loads((tmp_path / "cluster_nodes.json").read_text(encoding="utf-8"))
        assert set(data) == {"n1", "n2"}

    def test_corrupt_registry_file_treated_as_empty(self, tmp_path):
        path = tmp_path / "cluster_nodes.json"
        path.write_text("{not valid json", encoding="utf-8")
        registry = NodeRegistry(str(path))
        assert registry.alive() == []
        # 损坏后仍可正常注册（自愈覆盖）
        registry.register(_node("n1"))
        assert [n.node_id for n in registry.alive()] == ["n1"]


# ---------------------------------------------------------------------------
# ClusterRouter.pick：两种选点策略
# ---------------------------------------------------------------------------

class TestPick:
    def test_least_load_picks_lowest(self, registry, router):
        registry.register(_node("busy", load=0.9))
        registry.register(_node("idle", host="10.0.0.2", load=0.1))
        registry.register(_node("mid", host="10.0.0.3", load=0.5))
        assert router.pick(MODEL, prefer="least_load").node_id == "idle"

    def test_pick_filters_by_model_and_liveness(self, registry, router):
        registry.register(_node("no-model", models=["hermes-lite"], load=0.0))
        registry.register(_node("dead", host="10.0.0.2", load=0.0, age=120.0))
        registry.register(_node("ok", host="10.0.0.3", load=0.8))
        picked = router.pick(MODEL)
        assert picked is not None and picked.node_id == "ok"

    def test_pick_returns_none_without_candidates(self, router):
        assert router.pick(MODEL) is None

    def test_local_first_prefers_local_even_if_busier(self, registry, router):
        registry.register(_node("local", host="127.0.0.1", load=0.9))
        registry.register(_node("remote", host="10.0.0.2", load=0.0))
        assert router.pick(MODEL, prefer="local_first").node_id == "local"
        # 同一场景下 least_load 选远端
        assert router.pick(MODEL, prefer="least_load").node_id == "remote"

    def test_local_first_falls_back_to_remote(self, registry, router):
        registry.register(_node("remote-a", host="10.0.0.2", load=0.6))
        registry.register(_node("remote-b", host="10.0.0.3", load=0.2))
        picked = router.pick(MODEL, prefer="local_first")
        assert picked is not None and picked.node_id == "remote-b"

    def test_local_first_picks_least_loaded_among_locals(self, registry, router):
        registry.register(_node("local-busy", host="127.0.0.1", port=8080, load=0.9))
        registry.register(_node("local-idle", host="localhost", port=8081, load=0.2))
        assert router.pick(MODEL, prefer="local_first").node_id == "local-idle"

    def test_unknown_strategy_raises(self, registry, router):
        registry.register(_node("n1"))
        with pytest.raises(ValueError):
            router.pick(MODEL, prefer="random")


# ---------------------------------------------------------------------------
# route_chat：HTTP 调用一律 mock
# ---------------------------------------------------------------------------

def _openai_payload(
    content: str = "主人，我在呢。",
    reasoning: str = "主人在叫我，先温柔回应。",
    total_tokens: int = 42,
) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "reasoning_content": reasoning,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 32, "total_tokens": total_tokens},
    }


class _FakeResponse:
    """最小可用的 httpx.Response 替身。"""

    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=None, response=None
            )

    def json(self):
        return self._payload


class TestRouteChat:
    def test_route_chat_success(self, registry, router, monkeypatch):
        registry.register(_node("gpu-1", host="10.0.0.9", port=8080))
        captured = {}

        def fake_post(url, json, timeout):  # noqa: A002 —— 与 httpx 签名对齐
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return _FakeResponse(_openai_payload())

        monkeypatch.setattr(httpx, "post", fake_post)
        messages = [{"role": "user", "content": "在吗"}]
        result = router.route_chat(messages, MODEL)

        assert captured["url"] == "http://10.0.0.9:8080/v1/chat/completions"
        assert captured["json"]["model"] == MODEL
        assert captured["json"]["messages"] == messages
        assert captured["timeout"] == router.timeout
        # GenerateResult 字段（SPEC §3.4），鸭子类型断言，不绑定具体实现类
        assert result.text == "主人，我在呢。"
        assert result.reasoning == "主人在叫我，先温柔回应。"
        assert result.model == MODEL
        assert result.tokens == 42

    def test_route_chat_without_reasoning_content(self, registry, router, monkeypatch):
        registry.register(_node("n1"))
        payload = _openai_payload()
        del payload["choices"][0]["message"]["reasoning_content"]
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: _FakeResponse(payload))
        result = router.route_chat([{"role": "user", "content": "hi"}], MODEL)
        assert result.reasoning == ""
        assert result.text == "主人，我在呢。"

    def test_route_chat_raises_when_all_dead(self, registry, router, monkeypatch):
        registry.register(_node("dead-1", age=120.0))
        registry.register(_node("dead-2", host="10.0.0.2", age=999.0))

        def _must_not_be_called(*a, **kw):  # 全灭时绝不应发起 HTTP
            raise AssertionError("不应发起任何 HTTP 请求")

        monkeypatch.setattr(httpx, "post", _must_not_be_called)
        with pytest.raises(ClusterUnavailable):
            router.route_chat([{"role": "user", "content": "在吗"}], MODEL)

    def test_route_chat_raises_when_registry_empty(self, router):
        with pytest.raises(ClusterUnavailable):
            router.route_chat([{"role": "user", "content": "在吗"}], MODEL)

    def test_route_chat_http_error_wrapped(self, registry, router, monkeypatch):
        registry.register(_node("n1"))

        def fake_post(*a, **kw):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "post", fake_post)
        with pytest.raises(ClusterUnavailable, match="n1"):
            router.route_chat([{"role": "user", "content": "在吗"}], MODEL)

    def test_route_chat_http_500_wrapped(self, registry, router, monkeypatch):
        registry.register(_node("n1"))
        monkeypatch.setattr(
            httpx, "post", lambda *a, **kw: _FakeResponse({}, status_code=500)
        )
        with pytest.raises(ClusterUnavailable):
            router.route_chat([{"role": "user", "content": "在吗"}], MODEL)

    def test_route_chat_malformed_payload_wrapped(self, registry, router, monkeypatch):
        registry.register(_node("n1"))
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: _FakeResponse({"oops": 1}))
        with pytest.raises(ClusterUnavailable, match="无法解析"):
            router.route_chat([{"role": "user", "content": "在吗"}], MODEL)
