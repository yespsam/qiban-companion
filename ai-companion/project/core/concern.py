"""惦记系统（SPEC §3.4a）：伴侣会记住主人说过的重大事件，并主动回访。

设计原则：
- 规则驱动、可测试：按主题关键词检测「心事」（财务亏损/身体不适/感情矛盾/
  工作变动/睡眠问题/家里的事），命中即记为一条惦记；
- 同主题再次提及 → 刷新时间与摘要并重新进入待回访状态；
- context_string() 生成注入 system prompt 的自然语言，引导模型找合适时机
  主动问起（如「上次你说的股票亏钱，现在好点了吗」），而不是机械播报；
- JSON 持久化，损坏文件容错，不阻断启动。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass

from core.logging_utils import get_logger

log = get_logger(__name__)

_MAX_AGE_S = 30 * 24 * 3600  # 惦记最长保留 30 天

# 心事主题库：按声明顺序匹配，先到先得
_TOPIC_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("finance", "财务亏损", ("股票", "基金", "爆仓", "套牢", "割肉", "亏钱", "亏了", "赔钱", "大跌", "回血")),
    ("health", "身体不适", ("生病", "发烧", "胃疼", "头疼", "感冒", "医院", "难受", "腰疼")),
    ("love", "感情矛盾", ("吵架", "分手", "离婚", "前任", "冷战", "劈腿")),
    ("job", "工作变动", ("失业", "裁员", "辞职", "被开", "跳槽", "面试")),
    ("sleep", "睡眠问题", ("失眠", "睡不着", "噩梦", "熬夜")),
    ("family", "家里的事", ("我妈", "我爸", "父母", "妈妈生病", "爸爸生病", "家里出")),
)


@dataclass
class Concern:
    topic: str            # 主题 id（finance/health/...）
    name: str             # 展示名（财务亏损/...）
    snippet: str          # 主人原话摘要
    ts: float             # 最近一次提及时间戳
    asked: bool = False   # 是否已回访过本轮
    ask_count: int = 0    # 累计回访次数


class ConcernTracker:
    def __init__(self, persist_path: str):
        self.persist_path = persist_path
        self._concerns: dict[str, Concern] = {}
        self._load()

    # ---------------- 持久化 ----------------
    def _load(self) -> None:
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("concerns", []):
                try:
                    c = Concern(**{k: item[k] for k in
                                   ("topic", "name", "snippet", "ts", "asked", "ask_count")})
                except (KeyError, TypeError):
                    continue
                self._concerns[c.topic] = c
        except FileNotFoundError:
            pass
        except Exception:  # noqa: BLE001 - 损坏文件不阻断启动
            log.warning("惦记文件 %s 读取失败，使用空状态", self.persist_path)

    def _persist(self) -> None:
        try:
            parent = os.path.dirname(os.path.abspath(self.persist_path))
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump({"concerns": [asdict(c) for c in self._concerns.values()]},
                          f, ensure_ascii=False, indent=2)
        except OSError:
            log.warning("惦记写入 %s 失败", self.persist_path)

    # ---------------- 对外 ----------------
    def detect(self, user_text: str, now: float | None = None) -> Concern | None:
        """从主人消息中检测心事；命中则记录/刷新并返回 Concern，否则 None。"""
        if not user_text:
            return None
        now = time.time() if now is None else now
        for topic, name, keywords in _TOPIC_RULES:
            if any(k in user_text for k in keywords):
                existing = self._concerns.get(topic)
                if existing:
                    existing.ts = now
                    existing.snippet = user_text[:20]
                    existing.asked = False  # 重新提及 → 重新进入待回访
                    concern = existing
                else:
                    concern = Concern(topic=topic, name=name,
                                      snippet=user_text[:20], ts=now)
                    self._concerns[topic] = concern
                self._persist()
                return concern
        return None

    def pending(self, now: float | None = None) -> list[Concern]:
        """待回访的惦记（未回访且未过期，按时间升序）。"""
        now = time.time() if now is None else now
        return sorted(
            (c for c in self._concerns.values()
             if not c.asked and now - c.ts <= _MAX_AGE_S),
            key=lambda c: c.ts,
        )

    def mark_asked(self, topic: str) -> None:
        c = self._concerns.get(topic)
        if c:
            c.asked = True
            c.ask_count += 1
            self._persist()

    def context_string(self, now: float | None = None) -> str:
        """注入 system prompt 的惦记描述；无待回访事项时返回空串。"""
        items = self.pending(now)
        if not items:
            return ""
        lines = ["你惦记着主人的这些事，找合适时机用自然的语气主动问起（不要机械播报）："]
        now = time.time() if now is None else now
        for c in items:
            age = _human_age(now - c.ts)
            lines.append(f"- {c.name}：主人说「{c.snippet}」（{age}）")
        return "\n".join(lines)


def _human_age(seconds: float) -> str:
    if seconds < 3600:
        return "刚才"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    return f"{int(seconds // 86400)} 天前"
