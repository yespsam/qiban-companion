"""parse_thinking 拆分 + CompanionEngine 流程（SPEC §6 必测点）。"""
import pytest

from core.config import Settings
from core.emotion import EmotionTracker
from core.engine import ChatResult, CompanionEngine, parse_thinking
from core.llm.base import GenerateResult
from core.llm.mock_backend import MockBackend
from core.memory import MemoryStore
from core.persona import PersonaManager

# ---------------- parse_thinking ----------------


def test_parse_thinking_without_tags():
    assert parse_thinking("直接回复主人") == ("", "直接回复主人")


def test_parse_thinking_with_block():
    thinking, text = parse_thinking("<think>主人今天累了，我要安慰</think>主人辛苦啦")
    assert thinking == "主人今天累了，我要安慰"
    assert text == "主人辛苦啦"


def test_parse_thinking_multiline_and_spaces():
    thinking, text = parse_thinking("<think>\n  第一步\n  第二步\n</think>\n回复\n")
    assert thinking == "第一步\n  第二步"
    assert text == "回复"


def test_parse_thinking_unclosed_tag():
    thinking, text = parse_thinking("<think>写到一半断了")
    assert thinking == "写到一半断了"
    assert text == ""


def test_parse_thinking_multiple_blocks():
    thinking, text = parse_thinking("<think>块一</think>中间<text></text><think>块二</think>结尾")
    assert "块一" in thinking and "块二" in thinking
    assert "<think>" not in text and text.endswith("结尾")


def test_parse_thinking_empty():
    assert parse_thinking("") == ("", "")


# ---------------- CompanionEngine ----------------


class _FakeBackend:
    """固定输出 <think> 包装的后端，且记录收到的 messages。"""

    name = "fake"

    def __init__(self):
        self.last_messages = None

    def generate(self, messages, temperature=0.7, max_tokens=1024):
        self.last_messages = messages
        return GenerateResult(text="<think>主人问好，要热情回应</think>主人好呀！",
                              reasoning="", model="fake", tokens=42)

    def generate_stream(self, messages, **kw):
        self.last_messages = messages
        yield {"type": "thinking", "delta": "先想想"}
        yield {"type": "text", "delta": "主人"}
        yield {"type": "text", "delta": "好呀"}

    def health_check(self):
        return True


class _ReasoningBackend(_FakeBackend):
    """原生 reasoning_content 优先于 <think> 解析。"""

    def generate(self, messages, temperature=0.7, max_tokens=1024):
        self.last_messages = messages
        return GenerateResult(text="正文回复", reasoning="原生推理链",
                              model="fake", tokens=10)


class _FakeIntentRouter:
    def __init__(self, hit=True):
        self.parsed_with = None
        self.hit = hit

    def parse(self, text):
        self.parsed_with = text
        return {"action": "on"} if self.hit else None

    def execute(self, cmd):
        return {"ok": True, "action": cmd["action"]}


@pytest.fixture()
def engine_factory(tmp_path):
    def make(backend=None, intent_router=None, **settings_kw):
        settings = Settings(data_dir=str(tmp_path / "data"), **settings_kw)
        return CompanionEngine(
            settings,
            backend or _FakeBackend(),
            PersonaManager("config/personas"),
            MemoryStore(str(tmp_path / "memory.db")),
            EmotionTracker(str(tmp_path / "emotion.json")),
            intent_router=intent_router,
        )
    return make


def test_chat_returns_full_chat_result(engine_factory):
    engine = engine_factory()
    result = engine.chat("你好")
    assert isinstance(result, ChatResult)
    assert result.text == "主人好呀！"
    assert result.thinking == "主人问好，要热情回应"
    assert result.persona_id == "female_companion"
    assert result.emotion["mood"] in {"happy", "calm", "worried", "jealous",
                                      "sleepy", "excited"}
    assert 0 <= result.emotion["affection"] <= 100
    assert result.actions == []


def test_chat_builds_messages_with_iron_rules(engine_factory):
    backend = _FakeBackend()
    engine = engine_factory(backend=backend)
    engine.chat("今天好累")
    system_msg = backend.last_messages[0]
    assert system_msg["role"] == "system"
    assert "【第一铁律】" in system_msg["content"]
    assert "心情" in system_msg["content"]  # 情绪上下文注入
    assert backend.last_messages[-1] == {"role": "user", "content": "今天好累"}


def test_chat_injects_active_relationship(engine_factory):
    """SPEC §3.2a：引擎把 settings.active_relationship 传给 build_system_prompt。"""
    backend = _FakeBackend()
    engine = engine_factory(backend=backend, active_relationship="elder")
    engine.chat("你好")
    system_msg = backend.last_messages[0]["content"]
    assert "长辈" in system_msg            # elder.yaml 注入
    assert "【思考风格】" in system_msg      # 思考风格铁则统一追加


def test_chat_writes_memory(engine_factory, tmp_path):
    engine = engine_factory()
    engine.chat("我喜欢猫")
    recent = engine.memory.recent(10)
    assert len(recent) == 2
    assert recent[0].role == "master" and recent[0].content == "我喜欢猫"
    assert recent[1].role == "companion" and recent[1].content == "主人好呀！"


def test_chat_uses_native_reasoning_first(engine_factory):
    engine = engine_factory(backend=_ReasoningBackend())
    result = engine.chat("你好")
    assert result.thinking == "原生推理链"
    assert result.text == "正文回复"


def test_show_thinking_false_still_fills_thinking(engine_factory):
    engine = engine_factory(show_thinking=False)
    result = engine.chat("你好")
    assert result.thinking  # SPEC §3.3：仍填充，由 UI 决定不显示


def test_intent_router_executes_on_hit(engine_factory):
    router = _FakeIntentRouter(hit=True)
    engine = engine_factory(intent_router=router)
    result = engine.chat("把客厅的灯打开")
    assert router.parsed_with == "把客厅的灯打开"
    assert result.actions == [{"ok": True, "action": "on"}]


def test_intent_router_miss_gives_no_actions(engine_factory):
    engine = engine_factory(intent_router=_FakeIntentRouter(hit=False))
    assert engine.chat("随便聊聊").actions == []


def test_chat_stream_yields_deltas_then_done(engine_factory):
    engine = engine_factory()
    events = list(engine.chat_stream("你好"))
    assert events[0] == {"type": "thinking", "delta": "先想想"}
    text_deltas = [e["delta"] for e in events if e["type"] == "text"]
    assert "".join(text_deltas) == "主人好呀"
    done = events[-1]
    assert done["type"] == "done"
    result = done["result"]
    assert isinstance(result, ChatResult)
    assert result.text == "主人好呀"
    assert result.thinking == "先想想"
    # 流式同样落记忆
    assert len(engine.memory.recent(10)) == 2


def test_chat_stream_parses_inline_think_tags(engine_factory):
    class _InlineThinkBackend(_FakeBackend):
        def generate_stream(self, messages, **kw):
            yield {"type": "text", "delta": "<think>内心戏</think>给主人的回复"}

    engine = engine_factory(backend=_InlineThinkBackend())
    done = list(engine.chat_stream("你好"))[-1]
    assert done["result"].thinking == "内心戏"
    assert done["result"].text == "给主人的回复"


def test_engine_with_mock_backend_end_to_end(tmp_path):
    """mock 后端全链路：关键词命中 + 思考链解析。"""
    settings = Settings(data_dir=str(tmp_path / "data"))
    engine = CompanionEngine(
        settings, MockBackend(settings, seed=7),
        PersonaManager("config/personas"),
        MemoryStore(str(tmp_path / "memory.db")),
        EmotionTracker(str(tmp_path / "emotion.json")),
    )
    result = engine.chat("谢谢你陪我")
    assert result.text and result.thinking
    assert "主人" in result.text
    assert "<think>" not in result.text
