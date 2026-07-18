"""对话引擎（SPEC §3.3）。

流程：memory.retrieve → emotion.update → build_system_prompt
     → backend.generate → 解析 <think>…</think> → intent_router（可选）
     → memory.add 本轮 → 返回 ChatResult。
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Iterator

from core.config import Settings
from core.concern import ConcernTracker
from core.emotion import EmotionTracker
from core.llm.base import LLMBackend
from core.logging_utils import get_logger
from core.memory import Episode, MemoryStore
from core.persona import PersonaManager

log = get_logger(__name__)

_HISTORY_TURNS = 10      # 注入对话历史的最近条数
_RETRIEVE_K = 5          # 记忆召回条数

_THINK_BLOCK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN_RE = re.compile(r"<think>", re.IGNORECASE)


def parse_thinking(raw: str) -> tuple[str, str]:
    """把模型原始输出拆成 (thinking, text)。

    - 无 <think> 标签 → ("", 原文)
    - 一个/多个完整 <think>…</think> → 拼接所有思考块，其余为正文
    - 未闭合的 <think> → 其后的内容全部视为 thinking，正文为空
    """
    if not raw:
        return "", ""
    blocks = _THINK_BLOCK_RE.findall(raw)
    thinking = "\n".join(b.strip() for b in blocks if b.strip())
    text = _THINK_BLOCK_RE.sub("", raw)
    # 未闭合标签：剩余部分整体当作思考
    m = _THINK_OPEN_RE.search(text)
    if m:
        extra = text[m.end():].strip()
        if extra:
            thinking = f"{thinking}\n{extra}" if thinking else extra
        text = text[:m.start()]
    return thinking, text.strip()


@dataclass
class ChatResult:
    text: str                 # 给主人看的最终回复
    thinking: str             # 思考链（可为 ""；show_thinking=False 时仍填充）
    emotion: dict             # {"mood": str, "affection": int(0-100)}
    actions: list[dict] = field(default_factory=list)  # 设备控制动作（引擎透传）
    persona_id: str = ""


class CompanionEngine:
    def __init__(self, settings: Settings,
                 backend: LLMBackend,
                 persona_manager: PersonaManager,
                 memory: MemoryStore,
                 emotion: EmotionTracker,
                 intent_router=None, concern_tracker: ConcernTracker | None = None):
        self.settings = settings
        self.backend = backend
        self.persona_manager = persona_manager
        self.memory = memory
        self.emotion = emotion
        self.intent_router = intent_router
        # 惦记系统（SPEC §3.4a）：默认落到 data_dir/concerns.json，失败优雅禁用
        if concern_tracker is not None:
            self.concern_tracker = concern_tracker
        else:
            try:
                self.concern_tracker = ConcernTracker(
                    os.path.join(settings.data_dir, "concerns.json"))
            except Exception:  # noqa: BLE001
                log.exception("惦记系统初始化失败，已禁用")
                self.concern_tracker = None

    # ---------------- 内部步骤 ----------------

    def _prepare(self, user_text: str) -> tuple[list[dict], object]:
        """记忆召回 + 情绪更新 + 惦记检测 + 拼装 messages。"""
        memories = self.memory.retrieve(user_text, k=_RETRIEVE_K)
        memory_context = "\n".join(f"- {m.content}" for m in memories)

        state = self.emotion.update(user_text, "")
        emotion_context = self.emotion.context_string()

        # 惦记系统：检测本轮心事；待回访事项注入 prompt 并引导主动问起
        if self.concern_tracker is not None:
            try:
                detected = self.concern_tracker.detect(user_text)
                concern_ctx = self.concern_tracker.context_string()
                if concern_ctx:
                    memory_context = f"{memory_context}\n{concern_ctx}".strip("\n")
                # 本轮新记下的心事不在当轮回访（本轮回复已在共情），
                # 待后续轮次自然提起，避免机械感
                due = [c for c in self.concern_tracker.pending()
                       if detected is None or c.topic != detected.topic]
                if due:
                    names = "、".join(c.name for c in due)
                    memory_context += (
                        f"\n【主动关心】本次回复时，先用一两句话自然地提起你惦记的"
                        f"{names}（比如「对了主人，上次说的那件事现在好点了吗」），"
                        f"再回应主人本条消息。")
                    for c in due:
                        self.concern_tracker.mark_asked(c.topic)
            except Exception:  # noqa: BLE001 - 惦记故障不影响对话
                log.exception("惦记系统处理失败")

        system_prompt = self.persona_manager.build_system_prompt(
            self.settings.active_persona, self.settings.master_name,
            emotion_context, memory_context,
            relationship_id=getattr(self.settings, "active_relationship", None),
        )
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for ep in self.memory.recent(_HISTORY_TURNS):
            role = "user" if ep.role == "master" else "assistant"
            messages.append({"role": role, "content": ep.content})
        messages.append({"role": "user", "content": user_text})
        return messages, state

    def _run_intent(self, user_text: str) -> list[dict]:
        """可选的设备意图路由：命中则执行动作并透传结果。"""
        if self.intent_router is None:
            return []
        try:
            cmd = self.intent_router.parse(user_text)
            if cmd is None:
                return []
            return [self.intent_router.execute(cmd)]
        except Exception:  # noqa: BLE001 - 设备故障不应影响对话
            log.exception("意图路由执行失败")
            return []

    def _record_round(self, user_text: str, reply_text: str, mood: str) -> None:
        now = time.time()
        self.memory.add(Episode(ts=now, role="master", content=user_text,
                                emotion=mood))
        self.memory.add(Episode(ts=now + 1e-3, role="companion",
                                content=reply_text, emotion=mood))

    @staticmethod
    def _emotion_dict(state) -> dict:
        return {"mood": state.mood,
                "affection": max(0, min(100, int(state.affection))),
                "user_mood": getattr(state, "user_mood", "平静")}

    # ---------------- 对外接口 ----------------

    def chat(self, user_text: str) -> ChatResult:
        messages, state = self._prepare(user_text)
        result = self.backend.generate(
            messages,
            temperature=getattr(self.settings, "llm_temperature", 0.72),
            max_tokens=getattr(self.settings, "llm_max_tokens", 900),
        )
        if result.reasoning:
            thinking = result.reasoning
            extra, text = parse_thinking(result.text)
            thinking = thinking or extra
        else:
            thinking, text = parse_thinking(result.text)

        actions = self._run_intent(user_text)
        self._record_round(user_text, text, state.mood)
        return ChatResult(
            text=text,
            thinking=thinking,
            emotion=self._emotion_dict(state),
            actions=actions,
            persona_id=self.settings.active_persona,
        )

    def chat_stream(self, user_text: str) -> Iterator[dict]:
        """逐 token 产出 {"type":"thinking"|"text","delta":str}，
        最后产出 {"type":"done","result":ChatResult}。"""
        messages, state = self._prepare(user_text)
        thinking_parts: list[str] = []
        text_parts: list[str] = []
        for chunk in self.backend.generate_stream(
            messages,
            temperature=getattr(self.settings, "llm_temperature", 0.72),
            max_tokens=getattr(self.settings, "llm_max_tokens", 900),
        ):
            ctype = chunk.get("type")
            delta = str(chunk.get("delta", ""))
            if ctype == "thinking":
                thinking_parts.append(delta)
                yield {"type": "thinking", "delta": delta}
            else:
                text_parts.append(delta)
                yield {"type": "text", "delta": delta}

        thinking = "".join(thinking_parts)
        extra, text = parse_thinking("".join(text_parts))
        thinking = thinking or extra

        actions = self._run_intent(user_text)
        self._record_round(user_text, text, state.mood)
        yield {"type": "done", "result": ChatResult(
            text=text,
            thinking=thinking,
            emotion=self._emotion_dict(state),
            actions=actions,
            persona_id=self.settings.active_persona,
        )}
