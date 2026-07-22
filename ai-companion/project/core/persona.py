"""人格系统（SPEC §3.2 + §3.2a）。

人格文件为 config/personas/*.yaml。人格核心为三铁律（主人第一顺位），
validate_persona 校验铁律齐全且置于系统提示词最前。

关系身份文件为 config/relationships/*.yaml（§3.2a，与性别正交）：
lover/friend/bestie/elder 四种身份决定伴侣与主人的相处方式与心声风格，
经 build_system_prompt 注入系统提示词（位于人格 prompt 之后）。
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

import yaml

from core.logging_utils import get_logger

log = get_logger(__name__)

# 三铁律标记：必须出现在 system_prompt 中，且按序排列、置于最前
IRON_RULE_MARKERS = ("【第一铁律】", "【第二铁律】", "【第三铁律】")
_VALID_GENDERS = {"female", "male"}

# 默认关系身份（relationship_id=None 时回退）
DEFAULT_RELATIONSHIP = "lover"

# 思考风格铁则：build_system_prompt 末尾统一追加（SPEC §3.2a）。
# 伪思考链必须是第一人称心声，按「三拍心声」自然流淌（察觉→感受→决定），
# 禁止写成指导说明/分析提纲/第三人称描述。
THINKING_STYLE_RULE = (
    "【思考风格】<think> 里是你的真实心声，按自然的三拍流淌："
    "第一拍「察觉」——先注意到主人话里的细节或状态（可以引用主人的原词），不是复述问题；"
    "第二拍「感受」——你此刻真实的情绪反应：心疼、开心、委屈、犹豫、担心都可以；"
    "第三拍「决定」——你打算怎么回应，可以带一点犹豫或自我叮嘱"
    "（比如「别急着讲道理」「先抱抱他」）。"
    "心声用第一人称、口语，可长可短（一两句到三四句），"
    "允许没说完的半句话和省略号；"
    "禁止写成指导说明、分析提纲或第三人称描述，禁止和上一次心声句式雷同。"
)

VOICE_SHAPED_RULE = (
    "【声音驱动表达】你的文字要像能被自然朗读出来的声音：短句优先，"
    "一段只承载一个情绪动作；先接住主人的情绪，再给具体建议。"
    "不要堆砌华丽形容词，不要像客服、说明书或模型自述。"
)

# 对话技艺知识库默认路径（SPEC §3.2b）：提炼自心理学与文学，
# 注入系统提示词，让模型按真人方式对话（共情反映/具体化/留白/潜台词）。
DEFAULT_CRAFT_PATH = "config/dialogue_craft.yaml"


@dataclass
class Persona:
    id: str
    display_name: str
    gender: str
    address_master_as: str
    voice: dict = field(default_factory=dict)
    system_prompt: str = ""
    traits: list[str] = field(default_factory=list)
    thinking_style: str = ""


class PersonaManager:
    def __init__(self, personas_dir: str = "config/personas",
                 relationships_dir: str | None = None,
                 craft_path: str | None = None):
        self.personas_dir = personas_dir
        # 关系身份目录默认取 personas 目录的兄弟目录 relationships
        # （config/personas → config/relationships）
        if relationships_dir is None:
            base = os.path.dirname(personas_dir.rstrip("/")) or "."
            relationships_dir = os.path.join(base, "relationships")
        self.relationships_dir = relationships_dir
        # 对话技艺知识库默认取 config/dialogue_craft.yaml（§3.2b）
        if craft_path is None:
            base = os.path.dirname(personas_dir.rstrip("/")) or "."
            craft_path = os.path.join(base, "dialogue_craft.yaml")
        self.craft_path = craft_path
        self._craft_text: str | None = None  # 懒加载缓存
        self._personas: dict[str, Persona] = {}
        self._relationships: dict[str, dict] = {}
        self._load_all()
        self._load_relationships()

    def _load_craft(self) -> str:
        """加载对话技艺知识库并展平为提示词文本；文件缺失/损坏时返回空串。"""
        if self._craft_text is not None:
            return self._craft_text
        try:
            with open(self.craft_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            parts = []
            for key in ("psychology", "literary", "forbidden"):
                text = str(data.get(key) or "").strip()
                if text:
                    parts.append(text)
            self._craft_text = "\n".join(parts)
        except FileNotFoundError:
            log.warning("对话技艺库 %s 不存在，跳过注入", self.craft_path)
            self._craft_text = ""
        except Exception:  # noqa: BLE001
            log.exception("对话技艺库 %s 读取失败，跳过注入", self.craft_path)
            self._craft_text = ""
        return self._craft_text

    def _load_all(self) -> None:
        for path in sorted(glob.glob(os.path.join(self.personas_dir, "*.yaml"))):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                persona = self._from_dict(data, path)
                if not self.validate_persona(persona):
                    log.warning("人格文件 %s 未通过校验（铁律/字段不全），仍加载", path)
                self._personas[persona.id] = persona
            except Exception:  # noqa: BLE001 - 单个文件损坏不应拖垮全部人格
                log.exception("加载人格文件 %s 失败，已跳过", path)

    @staticmethod
    def _from_dict(data: dict, path: str = "") -> Persona:
        pid = str(data.get("id") or os.path.splitext(os.path.basename(path))[0])
        traits = data.get("traits") or []
        if isinstance(traits, str):
            traits = [traits]
        voice = data.get("voice") or {}
        if not isinstance(voice, dict):
            voice = {}
        return Persona(
            id=pid,
            display_name=str(data.get("display_name") or pid),
            gender=str(data.get("gender") or ""),
            address_master_as=str(data.get("address_master_as") or "主人"),
            voice=voice,
            system_prompt=str(data.get("system_prompt") or ""),
            traits=[str(t) for t in traits],
            thinking_style=str(data.get("thinking_style") or ""),
        )

    def _load_relationships(self) -> None:
        """加载 config/relationships/*.yaml（SPEC §3.2a）。

        单个文件损坏不拖垮其余身份；目录缺失时退化为无身份注入。
        """
        for path in sorted(glob.glob(os.path.join(self.relationships_dir, "*.yaml"))):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if not isinstance(data, dict):
                    raise ValueError("关系身份文件内容不是 mapping")
                rid = str(data.get("id") or os.path.splitext(os.path.basename(path))[0])
                self._relationships[rid] = {
                    "id": rid,
                    "display_name": str(data.get("display_name") or rid),
                    "prompt": str(data.get("prompt") or ""),
                    "thinking_guide": str(data.get("thinking_guide") or ""),
                }
            except Exception:  # noqa: BLE001 - 单个文件损坏不应拖垮全部身份
                log.exception("加载关系身份文件 %s 失败，已跳过", path)

    def list_personas(self) -> list[Persona]:
        return list(self._personas.values())

    def get(self, persona_id: str) -> Persona:
        """按 id 取人格；不存在抛 KeyError。"""
        if persona_id not in self._personas:
            raise KeyError(f"人格不存在: {persona_id}")
        return self._personas[persona_id]

    def list_relationships(self) -> list[dict]:
        """列出全部关系身份（§3.2a），元素为 {id, display_name, prompt, thinking_guide}。"""
        return [dict(r) for r in self._relationships.values()]

    def get_relationship(self, rel_id: str) -> dict:
        """按 id 取关系身份；不存在抛 KeyError。"""
        if rel_id not in self._relationships:
            raise KeyError(f"关系身份不存在: {rel_id}")
        return dict(self._relationships[rel_id])

    def build_system_prompt(self, persona_id: str, master_name: str,
                            emotion_context: str, memory_context: str,
                            relationship_id: str | None = None) -> str:
        """拼装最终系统提示词（§3.2 + §3.2a）。

        结构：人格本体（称呼替换）→ 关系身份（prompt + thinking_guide）
        → 情绪/记忆上下文 → 末尾统一追加思考风格铁则。
        relationship_id=None 时回退 DEFAULT_RELATIONSHIP（"lover"）；
        身份不存在时记日志并跳过注入（不阻断对话）。
        """
        persona = self.get(persona_id)
        master = master_name or persona.address_master_as or "主人"
        prompt = persona.system_prompt
        if master != "主人":
            prompt = prompt.replace("主人", master)

        sections = [prompt.strip()]

        rel_id = relationship_id or DEFAULT_RELATIONSHIP
        try:
            rel = self.get_relationship(rel_id)
        except KeyError:
            log.warning("关系身份 %s 不存在，跳过身份注入", rel_id)
        else:
            rel_lines = [f"【你与{master}的关系 · {rel['display_name']}】"]
            if rel["prompt"].strip():
                body = rel["prompt"].strip()
                if master != "主人":
                    body = body.replace("主人", master)
                rel_lines.append(body)
            if rel["thinking_guide"].strip():
                guide = rel["thinking_guide"].strip()
                if master != "主人":
                    guide = guide.replace("主人", master)
                rel_lines.append(f"【你的心声风格】\n{guide}")
            sections.append("\n".join(rel_lines))

        # 对话技艺（心理学+文学，§3.2b）：教人味，不教套话
        craft = self._load_craft()
        if craft:
            sections.append(f"【对话技艺（你学过心理学与文学）】\n{craft}")

        if emotion_context:
            sections.append(f"【你当前的状态】\n{emotion_context.strip()}")
        if memory_context:
            sections.append(f"【你记得的关于{master}的事】\n{memory_context.strip()}")
        sections.append(VOICE_SHAPED_RULE)
        sections.append(THINKING_STYLE_RULE)
        return "\n\n".join(sections)

    def validate_persona(self, p: Persona) -> bool:
        """校验字段齐全 + 三铁律存在且按序置于最前。"""
        if not p:
            return False
        # 字段齐全
        if not (p.id and p.display_name and p.address_master_as and p.system_prompt):
            return False
        if p.gender not in _VALID_GENDERS:
            return False
        if not isinstance(p.voice, dict) or not p.voice:
            return False
        if not p.traits or not p.thinking_style:
            return False
        # 三铁律存在且按序
        positions = []
        for marker in IRON_RULE_MARKERS:
            idx = p.system_prompt.find(marker)
            if idx < 0:
                return False
            positions.append(idx)
        if positions != sorted(positions):
            return False
        # 铁律置于最前
        if not p.system_prompt.lstrip().startswith(IRON_RULE_MARKERS[0]):
            return False
        return True
