"""人格铁律注入与校验 + 关系身份注入（SPEC §3.2 / §3.2a / §6 必测点）。"""
import pytest

from core.persona import (DEFAULT_RELATIONSHIP, THINKING_STYLE_RULE, Persona,
                          PersonaManager)

PERSONAS_DIR = "config/personas"


@pytest.fixture(scope="module")
def manager():
    return PersonaManager(PERSONAS_DIR)


def _valid_persona(**overrides) -> Persona:
    base = dict(
        id="test", display_name="测试", gender="female", address_master_as="主人",
        voice={"edge_tts_voice": "zh-CN-XiaoxiaoNeural"},
        system_prompt=("【第一铁律】主人第一顺位。\n【第二铁律】站在主人一边。\n"
                       "【第三铁律】守护主人。\n\n你是测试人格。"),
        traits=["温柔"], thinking_style="先共情",
    )
    base.update(overrides)
    return Persona(**base)


def test_bundled_personas_load_and_validate(manager):
    personas = manager.list_personas()
    ids = {p.id for p in personas}
    assert {"female_companion", "male_companion"} <= ids
    for p in personas:
        assert manager.validate_persona(p), f"内置人格 {p.id} 必须通过校验"


def test_get_missing_raises_keyerror(manager):
    with pytest.raises(KeyError):
        manager.get("no_such_persona")


def test_build_system_prompt_injects_iron_rules_and_contexts(manager):
    prompt = manager.build_system_prompt(
        "female_companion", "主人", "心情：开心；好感度 80/100", "- 主人喜欢猫")
    # 三铁律注入且置于最前
    assert prompt.lstrip().startswith("【第一铁律】")
    assert "【第二铁律】" in prompt and "【第三铁律】" in prompt
    # 情绪与记忆上下文注入
    assert "心情：开心" in prompt
    assert "主人喜欢猫" in prompt


def test_build_system_prompt_replaces_master_name(manager):
    prompt = manager.build_system_prompt("female_companion", "阿宅", "", "")
    assert "阿宅" in prompt


def test_build_system_prompt_missing_persona_raises(manager):
    with pytest.raises(KeyError):
        manager.build_system_prompt("ghost", "主人", "", "")


# ---------------------------------------------------------------- 关系身份（§3.2a）

def test_bundled_relationships_load(manager):
    rels = manager.list_relationships()
    ids = {r["id"] for r in rels}
    assert ids == {"lover", "friend", "bestie", "elder"}
    for r in rels:
        assert r["display_name"] and r["prompt"] and r["thinking_guide"]


def test_get_relationship_returns_dict(manager):
    rel = manager.get_relationship("lover")
    assert rel["id"] == "lover" and rel["display_name"] == "情侣"
    assert "吃醋" in rel["prompt"]


def test_get_relationship_unknown_raises_keyerror(manager):
    with pytest.raises(KeyError):
        manager.get_relationship("no_such_relationship")


@pytest.mark.parametrize("rel_id, marker", [
    ("lover", "吃醋"),
    ("friend", "互损"),
    ("bestie", "秘密"),
    ("elder", "唠叨"),
])
def test_build_system_prompt_injects_each_relationship(manager, rel_id, marker):
    prompt = manager.build_system_prompt(
        "female_companion", "主人", "", "", relationship_id=rel_id)
    assert marker in prompt
    # 身份区块位于人格 prompt 之后（铁律仍居最前）
    assert prompt.lstrip().startswith("【第一铁律】")
    assert prompt.index("【第一铁律】") < prompt.index(marker)
    # 心声风格指引一并注入
    assert "【你的心声风格】" in prompt


def test_build_system_prompt_defaults_to_lover(manager):
    default_prompt = manager.build_system_prompt("female_companion", "主人", "", "")
    lover_prompt = manager.build_system_prompt(
        "female_companion", "主人", "", "", relationship_id=DEFAULT_RELATIONSHIP)
    assert default_prompt == lover_prompt
    assert "情侣" in default_prompt


def test_build_system_prompt_unknown_relationship_degrades_gracefully(manager):
    """未知 relationship_id：记日志跳过注入，但铁律与思考风格铁则仍在。"""
    prompt = manager.build_system_prompt(
        "female_companion", "主人", "", "", relationship_id="ghost")
    assert prompt.lstrip().startswith("【第一铁律】")
    assert THINKING_STYLE_RULE in prompt


def test_build_system_prompt_appends_thinking_style_rule(manager):
    """思考风格铁则（写死常量）必须在系统提示词末尾。"""
    prompt = manager.build_system_prompt(
        "female_companion", "主人", "心情：开心", "- 主人喜欢猫", relationship_id="lover")
    assert THINKING_STYLE_RULE in prompt
    assert "第一人称" in prompt and "禁止写成指导说明" in prompt
    # 位于记忆上下文之后（即全词提示词末尾）
    assert prompt.index(THINKING_STYLE_RULE) > prompt.index("主人喜欢猫")


def test_build_system_prompt_relationship_master_name_replaced(manager):
    prompt = manager.build_system_prompt(
        "female_companion", "阿宅", "", "", relationship_id="lover")
    assert "阿宅" in prompt
    assert "【你与阿宅的关系" in prompt


@pytest.mark.parametrize("marker_to_drop", ["【第一铁律】", "【第二铁律】", "【第三铁律】"])
def test_validate_rejects_missing_iron_rule(manager, marker_to_drop):
    p = _valid_persona()
    p.system_prompt = p.system_prompt.replace(marker_to_drop, "")
    assert not manager.validate_persona(p)


def test_validate_rejects_iron_rules_not_at_front(manager):
    p = _valid_persona(system_prompt=(
        "开场白在前。\n【第一铁律】a\n【第二铁律】b\n【第三铁律】c"))
    assert not manager.validate_persona(p)


def test_validate_rejects_wrong_order(manager):
    p = _valid_persona(system_prompt=(
        "【第二铁律】b\n【第一铁律】a\n【第三铁律】c"))
    assert not manager.validate_persona(p)


@pytest.mark.parametrize("field, value", [
    ("display_name", ""), ("gender", "other"), ("address_master_as", ""),
    ("voice", {}), ("traits", []), ("thinking_style", ""), ("system_prompt", ""),
])
def test_validate_rejects_incomplete_fields(manager, field, value):
    p = _valid_persona(**{field: value})
    assert not manager.validate_persona(p)


def test_validate_accepts_valid_persona(manager):
    assert manager.validate_persona(_valid_persona())
