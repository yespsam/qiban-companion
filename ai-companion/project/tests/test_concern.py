"""惦记系统 + 用户情绪 + 财务共情场景测试（SPEC §3.4a）。"""
from __future__ import annotations

import json

import pytest

from core.concern import ConcernTracker
from core.config import Settings
from core.emotion import EmotionTracker
from core.engine import CompanionEngine
from core.llm.mock_backend import MockBackend
from core.memory import MemoryStore
from core.persona import PersonaManager


# ---------------- ConcernTracker ----------------

def test_detect_finance(tmp_path):
    t = ConcernTracker(str(tmp_path / "c.json"))
    c = t.detect("我股票亏钱了，好难受")
    assert c is not None and c.topic == "finance" and c.name == "财务亏损"
    assert "股票" in c.snippet


def test_detect_miss(tmp_path):
    t = ConcernTracker(str(tmp_path / "c.json"))
    assert t.detect("今天天气不错") is None
    assert t.detect("") is None


def test_detect_refresh_same_topic(tmp_path):
    t = ConcernTracker(str(tmp_path / "c.json"))
    t.detect("股票亏了", now=1000.0)
    t.mark_asked("finance")
    c = t.detect("基金又亏了", now=2000.0)
    assert c.ts == 2000.0 and c.asked is False and len(t._concerns) == 1


def test_pending_and_mark_asked(tmp_path):
    t = ConcernTracker(str(tmp_path / "c.json"))
    t.detect("我发烧了", now=1000.0)
    assert [c.topic for c in t.pending(now=1001.0)] == ["health"]
    t.mark_asked("health")
    assert t.pending(now=1002.0) == []


def test_pending_expires(tmp_path):
    t = ConcernTracker(str(tmp_path / "c.json"))
    t.detect("我失眠了", now=1000.0)
    assert t.pending(now=1000.0 + 31 * 24 * 3600) == []


def test_context_string(tmp_path):
    t = ConcernTracker(str(tmp_path / "c.json"))
    assert t.context_string() == ""
    t.detect("股票亏钱了", now=1000.0)
    s = t.context_string(now=1000.0 + 3700)
    assert "惦记" in s and "财务亏损" in s and "主动问起" in s


def test_persistence_and_corruption(tmp_path):
    p = str(tmp_path / "c.json")
    t = ConcernTracker(p)
    t.detect("我失业了")
    t2 = ConcernTracker(p)
    assert "job" in t2._concerns
    with open(p, "w", encoding="utf-8") as f:
        f.write("{broken json")
    t3 = ConcernTracker(p)  # 损坏文件不炸
    assert t3.pending() == []


# ---------------- 用户情绪识别（emotion.user_mood） ----------------

def test_user_mood_detect_low(tmp_path):
    e = EmotionTracker(str(tmp_path / "e.json"))
    st = e.update("我股票亏钱了", "")
    assert st.user_mood == "低落"


def test_user_mood_sticky_without_signal(tmp_path):
    e = EmotionTracker(str(tmp_path / "e.json"))
    e.update("我好焦虑，睡不着", "")
    st = e.update("今天吃了碗面", "")
    assert st.user_mood == "焦虑"  # 无新信号时保持


def test_user_mood_in_context_string(tmp_path):
    e = EmotionTracker(str(tmp_path / "e.json"))
    e.update("我股票亏钱了", "")
    s = e.context_string()
    assert "主人当下情绪：低落" in s and "先温柔接住" in s


def test_user_mood_old_file_compatible(tmp_path):
    p = tmp_path / "e.json"
    p.write_text(json.dumps({"mood": "happy", "affection": 66}), encoding="utf-8")
    e = EmotionTracker(str(p))
    assert e.current().user_mood == "平静"  # 旧文件无字段容错


# ---------------- mock 财务场景（四身份） ----------------

@pytest.mark.parametrize("rel", ["lover", "friend", "bestie", "elder"])
def test_mock_finance_scene(rel):
    s = Settings(active_relationship=rel)
    b = MockBackend(settings=s, seed=1)
    r = b.generate([{"role": "user", "content": "我股票亏钱了"}])
    assert "<think>" in r.text and "</think>" in r.text
    assert any(k in r.text for k in ("钱", "学费", "王八蛋", "投资", "赚", "庄家"))
    # 绝不应掉进干巴巴的兜底模板
    assert "然后呢" not in r.text.split("</think>")[-1] or rel == "elder"


@pytest.mark.parametrize("rel", ["lover", "friend", "bestie", "elder"])
def test_mock_health_scene(rel):
    s = Settings(active_relationship=rel)
    b = MockBackend(settings=s, seed=2)
    r = b.generate([{"role": "user", "content": "我发烧了好难受"}])
    assert any(k in r.text for k in ("医院", "医生", "休息", "躺着", "养着", "歇", "药"))


# ---------------- 引擎集成：惦记注入 + 主动关心 ----------------

def _make_engine(tmp_path, rel="lover"):
    settings = Settings(data_dir=str(tmp_path), active_relationship=rel,
                        llm_backend="mock")
    backend = MockBackend(settings=settings, seed=3)
    engine = CompanionEngine(
        settings, backend, PersonaManager(),
        MemoryStore(str(tmp_path / "m.db")),
        EmotionTracker(str(tmp_path / "e.json")),
        concern_tracker=ConcernTracker(str(tmp_path / "c.json")),
    )
    return engine, backend


def test_engine_records_concern_and_injects(tmp_path):
    engine, backend = _make_engine(tmp_path)
    engine.chat("我股票亏钱了")
    assert "finance" in engine.concern_tracker._concerns
    # 第二轮：system prompt 应包含惦记描述与主动关心指令
    captured = {}

    class SpyBackend(MockBackend):
        def generate(self, messages, **kw):
            captured["system"] = messages[0]["content"]
            return super().generate(messages, **kw)

    engine.backend = SpyBackend(settings=engine.settings, seed=4)
    engine.chat("今天天气不错")
    sys_prompt = captured["system"]
    assert "惦记" in sys_prompt and "财务亏损" in sys_prompt
    assert "主动关心" in sys_prompt
    assert engine.concern_tracker._concerns["finance"].asked is True


def test_engine_emotion_dict_has_user_mood(tmp_path):
    engine, _ = _make_engine(tmp_path)
    r = engine.chat("我股票亏钱了")
    assert r.emotion["user_mood"] == "低落"
    assert 0 <= r.emotion["affection"] <= 100
