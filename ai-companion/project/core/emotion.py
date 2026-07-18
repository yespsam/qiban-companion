"""情绪/好感度状态机（SPEC §3.6）。

规则驱动、可测试：
- 正向词（谢谢/喜欢/爱你/夸…）加分；负向词（不理你/烦…）减分；
- 深夜时段 → sleepy 倾向；mood 由净分值映射；
- affection 恒钳制在 0-100，初始 50；状态持久化到 json。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime

from core.logging_utils import get_logger

log = get_logger(__name__)

INITIAL_AFFECTION = 50
_AFFECTION_MIN, _AFFECTION_MAX = 0, 100
_DELTA_CAP = 10  # 单次 update 的好感度变化上限

_POSITIVE_WORDS = (
    "谢谢", "感谢", "谢啦", "喜欢你", "喜欢", "爱你", "最爱", "可爱",
    "真棒", "太棒了", "厉害", "乖", "想你", "亲亲", "抱抱", "贴心", "温柔", "夸",
)
_NEGATIVE_WORDS = (
    "不理你", "讨厌", "烦", "滚", "闭嘴", "无聊透顶", "笨蛋", "生气",
    "哼", "冷落", "烦死",
)
_JEALOUS_WORDS = ("别的ai", "别人更好", "换一个", "新伴侣", "移情别恋")
_SLEEPY_WORDS = ("困", "想睡", "晚安", "熬夜", "睡不着", "好困")
_EXCITED_WORDS = ("太好啦", "太棒了", "耶", "开心", "激动", "好耶")
_COMPANION_WARM_WORDS = ("爱你", "喜欢你", "抱抱", "主人最好")

_LATE_NIGHT_HOURS = frozenset({23, 0, 1, 2, 3, 4, 5})

_MOOD_ZH = {
    "happy": "开心", "calm": "平静", "worried": "有点委屈、担心",
    "jealous": "吃醋", "sleepy": "困倦", "excited": "兴奋",
}
_AFFECTION_BANDS = (
    (80, "深深地依恋着主人"),
    (60, "很喜欢主人"),
    (40, "和主人相处得不错"),
    (20, "有点被冷落、想和主人多说说话"),
    (0, "很受伤，需要主人哄一哄"),
)


@dataclass
class EmotionState:
    mood: str = "calm"   # happy|calm|worried|jealous|sleepy|excited
    affection: int = INITIAL_AFFECTION  # 0-100
    user_mood: str = "平静"  # 主人当下情绪：开心|低落|焦虑|愤怒|平静（SPEC §3.4a）

# 主人情绪识别（按声明顺序匹配；用于情感系统，伴侣据此调整回应策略）
_USER_MOOD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("低落", ("难过", "伤心", "亏", "想哭", "撑不住", "沮丧", "emo", "没意思", "委屈")),
    ("焦虑", ("焦虑", "压力", "失眠", "睡不着", "担心", "紧张", "怎么办")),
    ("愤怒", ("气死", "讨厌", "滚", "凭什么", "气人", "烦死")),
    ("开心", ("开心", "高兴", "赚了", "太好", "哈哈", "棒", "好耶")),
)
_USER_MOOD_GUIDE = {
    "低落": "主人现在情绪低落，先温柔接住、陪伴为主，别讲道理。",
    "焦虑": "主人现在很焦虑，语气要稳、要有安全感，别添乱。",
    "愤怒": "主人在气头上，先顺毛、别顶嘴、别评理。",
    "开心": "主人心情好，陪主人一起开心，让快乐翻倍。",
}


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


class EmotionTracker:
    def __init__(self, persist_path: str):
        self.persist_path = persist_path
        self._state = EmotionState()
        self._load()

    def _load(self) -> None:
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            mood = str(data.get("mood", "calm"))
            if mood not in _MOOD_ZH:
                mood = "calm"
            self._state = EmotionState(
                mood=mood,
                affection=_clamp(int(data.get("affection", INITIAL_AFFECTION)),
                                 _AFFECTION_MIN, _AFFECTION_MAX),
            )
        except FileNotFoundError:
            pass
        except Exception:  # noqa: BLE001 - 损坏的持久化文件不应阻断启动
            log.warning("情绪状态文件 %s 读取失败，使用初始状态", self.persist_path)

    def _persist(self) -> None:
        try:
            parent = os.path.dirname(os.path.abspath(self.persist_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump({"mood": self._state.mood,
                           "affection": self._state.affection,
                           "user_mood": self._state.user_mood},
                          f, ensure_ascii=False, indent=2)
        except OSError:
            log.warning("情绪状态写入 %s 失败", self.persist_path)

    @staticmethod
    def _hits(text: str, words) -> int:
        return sum(1 for w in words if w in text)

    def update(self, user_text: str, companion_text: str,
               now: datetime | None = None) -> EmotionState:
        """根据一轮对话更新情绪与好感度并持久化。

        now 可注入（便于测试深夜 sleepy 规则），默认取当前时间。
        """
        user_text = user_text or ""
        pos = self._hits(user_text, _POSITIVE_WORDS)
        neg = self._hits(user_text, _NEGATIVE_WORDS)
        excited = self._hits(user_text, _EXCITED_WORDS)
        jealous = self._hits(user_text.lower(), _JEALOUS_WORDS)
        sleepy = self._hits(user_text, _SLEEPY_WORDS)
        warm = self._hits(companion_text or "", _COMPANION_WARM_WORDS)

        delta = 2 * pos + 2 * excited - 3 * neg + min(warm, 1)
        delta = _clamp(delta, -_DELTA_CAP, _DELTA_CAP)
        self._state.affection = _clamp(self._state.affection + delta,
                                       _AFFECTION_MIN, _AFFECTION_MAX)

        net = pos + excited - neg
        late_night = (now or datetime.now()).hour in _LATE_NIGHT_HOURS
        if jealous:
            mood = "jealous"
        elif net < 0:
            mood = "worried"
        elif net >= 3 or excited >= 2:
            mood = "excited"
        elif net > 0:
            mood = "happy"
        elif sleepy or late_night:
            mood = "sleepy"
        else:
            mood = "calm"
        self._state.mood = mood

        # 主人情绪识别：有信号则更新，无信号保持（情绪有惯性）
        for emo, words in _USER_MOOD_RULES:
            if any(w in user_text for w in words):
                self._state.user_mood = emo
                break

        self._persist()
        return EmotionState(self._state.mood, self._state.affection,
                            self._state.user_mood)

    def current(self) -> EmotionState:
        return EmotionState(self._state.mood, self._state.affection,
                            self._state.user_mood)

    def context_string(self) -> str:
        """注入 system prompt 的自然语言状态描述。"""
        band = next(desc for threshold, desc in _AFFECTION_BANDS
                    if self._state.affection >= threshold)
        base = (f"心情：{_MOOD_ZH.get(self._state.mood, self._state.mood)}；"
                f"对主人的好感度：{self._state.affection}/100（{band}）。")
        if self._state.user_mood != "平静":
            guide = _USER_MOOD_GUIDE.get(self._state.user_mood, "")
            base += f"主人当下情绪：{self._state.user_mood}。{guide}"
        return base
