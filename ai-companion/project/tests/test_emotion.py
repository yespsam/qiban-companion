"""EmotionTracker 加减分与钳制（SPEC §6 必测点）。"""
from datetime import datetime

from core.emotion import EmotionState, EmotionTracker

_NOON = datetime(2024, 5, 1, 12, 0)       # 白天，避免 sleepy 干扰
_LATE = datetime(2024, 5, 1, 2, 30)       # 深夜


def test_initial_state(tmp_path):
    tracker = EmotionTracker(str(tmp_path / "e.json"))
    state = tracker.current()
    assert state.mood == "calm"
    assert state.affection == 50


def test_positive_words_raise_affection_and_happy(tmp_path):
    tracker = EmotionTracker(str(tmp_path / "e.json"))
    state = tracker.update("谢谢你，我真的很喜欢你", "", now=_NOON)
    assert state.affection > 50
    assert state.mood in {"happy", "excited"}


def test_negative_words_lower_affection_and_worried(tmp_path):
    tracker = EmotionTracker(str(tmp_path / "e.json"))
    state = tracker.update("我不想理你了，真烦", "", now=_NOON)
    assert state.affection < 50
    assert state.mood == "worried"


def test_affection_clamped_at_100(tmp_path):
    tracker = EmotionTracker(str(tmp_path / "e.json"))
    state = None
    for _ in range(100):
        state = tracker.update("爱你爱你，你最棒了，谢谢", "", now=_NOON)
    assert state.affection == 100


def test_affection_clamped_at_0(tmp_path):
    tracker = EmotionTracker(str(tmp_path / "e.json"))
    state = None
    for _ in range(100):
        state = tracker.update("讨厌你，滚，烦死了", "", now=_NOON)
    assert state.affection == 0


def test_single_update_delta_capped(tmp_path):
    tracker = EmotionTracker(str(tmp_path / "e.json"))
    text = "谢谢 喜欢 爱你 真棒 可爱 想你 亲亲 抱抱 贴心 温柔 夸 耶 开心 激动"
    state = tracker.update(text, "", now=_NOON)
    assert state.affection == 60  # 50 + 单次上限 10


def test_late_night_sleepy_tendency(tmp_path):
    tracker = EmotionTracker(str(tmp_path / "e.json"))
    state = tracker.update("嗯", "", now=_LATE)
    assert state.mood == "sleepy"


def test_positive_at_late_night_stays_happy(tmp_path):
    tracker = EmotionTracker(str(tmp_path / "e.json"))
    state = tracker.update("好耶太棒了", "", now=_LATE)
    assert state.mood in {"happy", "excited"}  # 强信号压过 sleepy 倾向


def test_neutral_daytime_stays_calm(tmp_path):
    tracker = EmotionTracker(str(tmp_path / "e.json"))
    state = tracker.update("今天吃了面", "", now=_NOON)
    assert state.mood == "calm"


def test_persistence_round_trip(tmp_path):
    path = str(tmp_path / "e.json")
    tracker = EmotionTracker(path)
    tracker.update("喜欢你", "", now=_NOON)
    reloaded = EmotionTracker(path)
    assert reloaded.current() == tracker.current()
    assert reloaded.current().affection > 50


def test_corrupt_persist_file_falls_back_to_initial(tmp_path):
    path = tmp_path / "e.json"
    path.write_text("{不是合法 json", encoding="utf-8")
    tracker = EmotionTracker(str(path))
    assert tracker.current() == EmotionState("calm", 50)


def test_context_string_mentions_mood_and_affection(tmp_path):
    tracker = EmotionTracker(str(tmp_path / "e.json"))
    tracker.update("爱你", "", now=_NOON)
    ctx = tracker.context_string()
    assert "心情" in ctx
    assert str(tracker.current().affection) in ctx
    assert isinstance(ctx, str) and len(ctx) > 5


def test_update_returns_copy_not_internal_reference(tmp_path):
    tracker = EmotionTracker(str(tmp_path / "e.json"))
    state = tracker.update("谢谢", "", now=_NOON)
    state.affection = 0
    assert tracker.current().affection != 0
