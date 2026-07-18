"""Mock 后端：关系身份模板与第一人称心声（SPEC §3.2a / §3.4）。

- 四种身份（lover/friend/bestie/elder）均返回带 <think>…</think> 的输出；
- 伪思考链为第一人称心声（含情绪词），非指导说明式写法；
- 性别仅轻量影响自称（女→人家，男→我）；
- 未命中关键词走兜底；未知身份回退 lover。
"""
import pytest

from core.config import Settings
from core.llm.base import GenerateResult
from core.llm.mock_backend import (_DEFAULT_RELATIONSHIP, _RULES,
                                   _SCENE_KEYWORDS, MockBackend)

RELATIONSHIPS = ["lover", "friend", "bestie", "elder"]


def _generate(rel: str, text: str, seed: int = 1, **settings_kw) -> GenerateResult:
    settings = Settings(active_relationship=rel, **settings_kw)
    backend = MockBackend(settings, seed=seed)
    return backend.generate([{"role": "user", "content": text}])


# ------------------------------------------------------------------ 结构完整性
@pytest.mark.parametrize("rel", RELATIONSHIPS)
def test_rules_cover_all_scenes_with_three_replies(rel):
    """RULES[relationship][场景]：12 场景齐全，每场景 thinking + replies[3]。"""
    scenes = _RULES[rel]
    for scene in _SCENE_KEYWORDS:
        assert scene in scenes, f"{rel} 缺场景 {scene}"
        assert scenes[scene]["thinking"].strip()
        assert len(scenes[scene]["replies"]) >= 2  # v4 扩充场景为 2 条起
        assert all(r.strip() for r in scenes[scene]["replies"])
    assert len(scenes["fallback"]["replies"]) == 3


# ------------------------------------------------------------------ 契约
@pytest.mark.parametrize("rel", RELATIONSHIPS)
def test_each_relationship_returns_think_block(rel):
    result = _generate(rel, "今天好累")
    assert result.text.startswith("<think>") and "</think>" in result.text
    thinking, reply = result.text.split("</think>", 1)
    assert thinking[len("<think>"):].strip()
    assert reply.strip()
    assert result.reasoning == "" and result.tokens >= 1


@pytest.mark.parametrize("rel", RELATIONSHIPS)
def test_each_relationship_stream_matches_generate(rel):
    settings = Settings(active_relationship=rel)
    backend = MockBackend(settings, seed=3)
    chunks = list(backend.generate_stream([{"role": "user", "content": "晚安"}]))
    types = {c["type"] for c in chunks}
    assert types == {"thinking", "text"}
    thinking = "".join(c["delta"] for c in chunks if c["type"] == "thinking")
    text = "".join(c["delta"] for c in chunks if c["type"] == "text")
    assert thinking.strip() and text.strip()
    assert "<think>" not in text


# ------------------------------------------------------------------ 第一人称心声
@pytest.mark.parametrize("rel", RELATIONSHIPS)
def test_thinking_is_first_person_inner_voice(rel):
    result = _generate(rel, "我很难过")
    thinking = result.text.split("</think>", 1)[0][len("<think>"):]
    assert "我" in thinking
    # 禁止指导说明式措辞（来自旧的「先…再…」分析提纲风格）
    for banned in ("先共情", "再分析", "第一步", "第二步", "分析问题，再"):
        assert banned not in thinking


@pytest.mark.parametrize("rel, tone_word", [
    ("lover", "抱"),
    ("friend", "兄弟"),
    ("bestie", "！"),
    ("elder", "身子"),
])
def test_relationship_tone_differs(rel, tone_word):
    """四种身份「累」场景的模板语气应可区分（抽查特征词，确定性检查模板本身）。"""
    replies = _RULES[rel]["tired"]["replies"]
    assert any(tone_word in r for r in replies), f"{rel} 回复未见特征语气 {tone_word!r}"


def test_outputs_differ_across_relationships():
    outputs = {_generate(rel, "今天好累", seed=5).text for rel in RELATIONSHIPS}
    assert len(outputs) == 4


# ------------------------------------------------------------------ 身份解析与回退
def test_unknown_relationship_falls_back_to_default():
    ghost = _generate("ghost", "今天好累", seed=1)
    default = _generate(_DEFAULT_RELATIONSHIP, "今天好累", seed=1)
    assert ghost.text == default.text


def test_missing_settings_uses_default_relationship():
    backend = MockBackend(None, seed=1)
    result = backend.generate([{"role": "user", "content": "你好"}])
    assert "<think>" in result.text and "</think>" in result.text


def test_relationship_hot_switch_without_rebuild():
    """切换 settings.active_relationship 后同一后端实例即生效（热更新）。"""
    settings = Settings(active_relationship="lover")
    backend = MockBackend(settings, seed=1)
    before = backend.generate([{"role": "user", "content": "今天好累"}]).text
    settings.active_relationship = "elder"
    after = backend.generate([{"role": "user", "content": "今天好累"}]).text
    assert before != after


# ------------------------------------------------------------------ 替换规则
def test_master_name_replaced_in_output():
    # lover 打招呼场景 3 条回复均含 {master}，替换结果确定
    result = _generate("lover", "你好", master_name="阿宅")
    assert "阿宅" in result.text


@pytest.mark.parametrize("persona, expected", [
    ("female_companion", "人家"),
    ("male_companion", "我"),
])
def test_self_ref_gender_substitution(persona, expected):
    """性别只影响自称：{自称} 女→人家 / 男→我（不污染思考链）。"""
    settings = Settings(active_relationship="lover", active_persona=persona)
    backend = MockBackend(settings, seed=1)
    result = backend.generate([{"role": "user", "content": "我喜欢你"}])
    reply = result.text.split("</think>", 1)[1]
    assert expected in reply
    assert "{自称}" not in result.text and "{master}" not in result.text


def test_fallback_when_no_keyword():
    result = _generate("lover", "量子计算机的原理是什么呢")
    assert "<think>" in result.text and "</think>" in result.text
    assert result.text.split("</think>", 1)[1].strip()


def test_health_check():
    assert MockBackend(Settings()).health_check() is True
