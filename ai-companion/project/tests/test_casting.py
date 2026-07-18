"""声优选角测试（SPEC §3.7a）。

铁律同 test_voice_smoke：不 import 任何重依赖，不触网不触硬件。
"""
import inspect
import sys

import pytest

from voice.casting import clear_cache, prosody_kwargs, resolve_cast
from voice.tts import EdgeTTSEngine

VOICES_YAML = """\
cast:
  female_companion:
    default: { edge_tts_voice: zh-CN-XiaoxiaoNeural, style: gentle,   rate: "+0%", pitch: "+0Hz" }
    lover:   { edge_tts_voice: zh-CN-XiaoxiaoNeural, style: affectionate, rate: "-2%", pitch: "+2Hz" }
    bestie:  { edge_tts_voice: zh-CN-XiaoyiNeural,   style: cheerful, rate: "+8%", pitch: "+4Hz" }
  male_companion:
    default: { edge_tts_voice: zh-CN-YunxiNeural,   style: warm, rate: "+0%", pitch: "+0Hz" }
    elder:   { edge_tts_voice: zh-CN-YunjianNeural, style: calm, rate: "-8%", pitch: "-2Hz" }
emotion_prosody:
  care:    { rate: "-12%", pitch: "-2Hz" }
  excited: { rate: "+8%",  pitch: "+3Hz" }
archetypes:
  female:
    loli:  { name: 萝莉音, edge_tts_voice: zh-CN-XiaoyiNeural,   style: cheerful, rate: "+12%", pitch: "+18Hz" }
    yujie: { name: 御姐音, edge_tts_voice: zh-CN-XiaoxiaoNeural, style: calm,     rate: "-8%",  pitch: "-8Hz" }
  male:
    uncle: { name: 大叔音, edge_tts_voice: zh-CN-YunjianNeural, style: calm, rate: "-10%", pitch: "-8Hz" }
"""


@pytest.fixture()
def voices_file(tmp_path):
    p = tmp_path / "voices.yaml"
    p.write_text(VOICES_YAML, encoding="utf-8")
    clear_cache()
    yield str(p)
    clear_cache()


# ---------- 1. 基本选角 ----------

def test_cast_per_relationship(voices_file):
    cast = resolve_cast("female_companion", "bestie", voices_path=voices_file)
    assert cast["voice"] == "zh-CN-XiaoyiNeural"
    assert cast["style"] == "cheerful"
    assert cast["rate"] == "+8%" and cast["pitch"] == "+4Hz"


def test_cast_unknown_relationship_falls_back_to_default(voices_file):
    cast = resolve_cast("female_companion", "no_such_rel", voices_path=voices_file)
    assert cast["voice"] == "zh-CN-XiaoxiaoNeural"
    assert cast["style"] == "gentle"


def test_cast_none_relationship_uses_default(voices_file):
    cast = resolve_cast("male_companion", None, voices_path=voices_file)
    assert cast["voice"] == "zh-CN-YunxiNeural"


# ---------- 2. 情绪韵律叠加 ----------

def test_emotion_prosody_stacks(voices_file):
    # 情侣(-2%, +2Hz) + 心疼(-12%, -2Hz) = (-14%, +0Hz)
    cast = resolve_cast("female_companion", "lover", mood="care", voices_path=voices_file)
    assert cast["rate"] == "-14%"
    assert cast["pitch"] == "+0Hz"


def test_emotion_prosody_excited(voices_file):
    # 长辈(-8%, -2Hz) + 超开心(+8%, +3Hz) = (+0%, +1Hz)
    cast = resolve_cast("male_companion", "elder", mood="excited", voices_path=voices_file)
    assert cast["rate"] == "+0%"
    assert cast["pitch"] == "+1Hz"


def test_unknown_mood_no_change(voices_file):
    cast = resolve_cast("female_companion", "bestie", mood="困惑", voices_path=voices_file)
    assert cast["rate"] == "+8%"


# ---------- 3. 容错回退 ----------

def test_missing_yaml_falls_back_to_persona_voice(tmp_path):
    cast = resolve_cast(
        "female_companion", "lover",
        persona_voice={"edge_tts_voice": "zh-CN-XiaoyiNeural", "speaking_style": "lyrical"},
        voices_path=str(tmp_path / "nonexistent.yaml"),
    )
    assert cast["voice"] == "zh-CN-XiaoyiNeural"
    assert cast["style"] == "lyrical"
    assert cast["rate"] == "+0%" and cast["pitch"] == "+0Hz"


def test_broken_yaml_falls_back(tmp_path):
    bad = tmp_path / "voices.yaml"
    bad.write_text("cast: [不是映射的脏东西", encoding="utf-8")
    clear_cache()
    cast = resolve_cast(
        "female_companion", "lover",
        persona_voice={"edge_tts_voice": "zh-CN-XiaoxiaoNeural"},
        voices_path=str(bad),
    )
    assert cast["voice"] == "zh-CN-XiaoxiaoNeural"
    clear_cache()


def test_persona_missing_from_cast_falls_back(voices_file):
    cast = resolve_cast(
        "ghost_persona", "lover",
        persona_voice={"edge_tts_voice": "zh-CN-YunyangNeural"},
        voices_path=voices_file,
    )
    assert cast["voice"] == "zh-CN-YunyangNeural"


def test_result_keys_always_present(voices_file):
    cast = resolve_cast("female_companion", "lover", voices_path=voices_file)
    assert set(cast) == {"voice", "style", "rate", "pitch"}
    assert all(isinstance(v, str) for v in cast.values())


# ---------- 3b. 声线覆盖（SPEC §3.7b） ----------

def test_archetype_overrides_cast(voices_file):
    cast = resolve_cast("female_companion", "lover", archetype="loli", voices_path=voices_file)
    assert cast["voice"] == "zh-CN-XiaoyiNeural"
    assert cast["style"] == "cheerful"
    assert cast["rate"] == "+12%" and cast["pitch"] == "+18Hz"
    assert cast["archetype"] == "萝莉音"


def test_archetype_stacks_with_emotion(voices_file):
    # 御姐(-8%, -8Hz) + 心疼(-12%, -2Hz) = (-20%, -10Hz)
    cast = resolve_cast("female_companion", "lover", mood="care",
                        archetype="yujie", voices_path=voices_file)
    assert cast["voice"] == "zh-CN-XiaoxiaoNeural"
    assert cast["rate"] == "-20%" and cast["pitch"] == "-10Hz"


def test_archetype_gender_inferred_from_persona(voices_file):
    cast = resolve_cast("male_companion", "lover", archetype="uncle", voices_path=voices_file)
    assert cast["voice"] == "zh-CN-YunjianNeural"


def test_archetype_gender_explicit(voices_file):
    # 人格 id 不含男女线索时，显式 gender 生效
    cast = resolve_cast("custom_bot", None, archetype="uncle", gender="male",
                        persona_voice={"edge_tts_voice": "x"}, voices_path=voices_file)
    assert cast["voice"] == "zh-CN-YunjianNeural"


def test_unknown_archetype_ignored(voices_file):
    cast = resolve_cast("female_companion", "bestie", archetype="不存在的声线",
                        voices_path=voices_file)
    assert cast["voice"] == "zh-CN-XiaoyiNeural"
    assert "archetype" not in cast


# ---------- 4. 缓存 ----------

def test_yaml_cached(voices_file):
    resolve_cast("female_companion", "lover", voices_path=voices_file)
    import voice.casting as casting
    assert voices_file in casting._CACHE


# ---------- 5. 引擎契约 ----------

def test_edge_engine_supports_prosody():
    assert EdgeTTSEngine.supports_prosody is True
    sig = inspect.signature(EdgeTTSEngine.synthesize)
    assert "rate" in sig.parameters and "pitch" in sig.parameters


def test_prosody_kwargs_only_for_supported_engines():
    cast = {"voice": "v", "style": "s", "rate": "-14%", "pitch": "+0Hz"}
    assert prosody_kwargs(EdgeTTSEngine(), cast) == {"rate": "-14%", "pitch": "+0Hz"}

    class OldEngine:
        supports_prosody = False
    assert prosody_kwargs(OldEngine(), cast) == {}

    class NoFlag:
        pass
    assert prosody_kwargs(NoFlag(), cast) == {}


def test_no_heavy_imports():
    assert "edge_tts" not in sys.modules
    assert "torch" not in sys.modules
