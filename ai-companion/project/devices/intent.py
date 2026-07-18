"""语音指令 → 设备指令 意图路由（SPEC §3.8）。

规则 + 别名表实现，纯标准库，无任何重依赖。

支持的中文指令模板（20+ 条，均支持可选房间前缀「客厅/卧室/…」）：
  开/关：开灯、关灯、打开客厅的灯、把卧室的空调打开、把书房台灯关了、
         关闭客厅风扇、空调打开、灯开一下
  温度：空调调到26度、把空调温度调到24摄氏度、空调26度
  模式：空调调到制冷模式、空调制热、空调除湿
  风扇：风扇开一档、把客厅风扇调到三档、风扇打开摇头、风扇别摇头
  亮度：灯调亮点、把卧室的灯调暗一点、把灯亮度调到50、灯调到80
  颜色：把灯调成暖黄色、灯变成红色
  场景：关灯睡觉、我要睡了把灯关了、把所有灯都关了、打开所有灯
  切换：切换客厅灯状态、客厅灯切换

未命中任何规则时 parse() 返回 None；execute() 调 mihome.control，
异常不外抛。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

try:
    from core.logging_utils import get_logger
except Exception:  # pragma: no cover - 兜底
    import logging

    def get_logger(name: str) -> "logging.Logger":
        return logging.getLogger(name)


log = get_logger("devices.intent")


@dataclass
class DeviceCommand:
    target: str        # did 或设备别名（如「客厅灯」）
    action: str        # on/off/toggle/set_temperature/set_brightness/set_mode/set_fan_level/set_oscillate/set_color/brightness_up/brightness_down
    params: list = field(default_factory=list)
    confidence: float = 0.0  # 0-1


# ---------------- 词表 ----------------

_ROOM = r"(?P<room>客厅|卧室|主卧|次卧|书房|厨房|卫生间|浴室|儿童房|阳台|餐厅|房间)?"
_DE = r"(?:的)?"
# 注意：alternation 有序，长的放前面
_DEV = (
    r"(?P<dev>空气净化器|扫地机器人|循环扇|落地扇|净化器|加湿器|除湿机|扫地机"
    r"|吸顶灯|床头灯|台灯|吊灯|夜灯|灯泡|空调|风扇|电扇|窗帘|插座|排插|电视|音箱|灯)"
)

_CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5}

_AC_MODE = {"制冷": "cool", "制热": "heat", "除湿": "dry", "送风": "fan",
            "自动": "auto", "节能": "eco", "睡眠": "sleep"}

_COLORS = {  # 颜色词 -> RGB
    "红色": (255, 0, 0), "绿色": (0, 255, 0), "蓝色": (0, 0, 255),
    "黄色": (255, 255, 0), "紫色": (128, 0, 128), "粉色": (255, 192, 203),
    "橙色": (255, 165, 0), "白色": (255, 255, 255),
    "暖白色": (255, 244, 229), "暖黄色": (255, 223, 178),
}
_COLOR_WORDS = "|".join(sorted(_COLORS, key=len, reverse=True))

_PREFIX_RE = re.compile(
    r"^(?:请|麻烦你|麻烦|帮我|给我|你帮我|我要|我想|我想要|小栖"
    r"|嘿|那个|现在)+"
)
_PUNCT_RE = re.compile(r"[，。！？!?,、；;：:…~～\s　]+")
_TRAILING_RE = re.compile(r"[吧呀啊呢哦咯]+$")


def _normalize(text: str) -> str:
    t = (text or "").strip()
    t = _PUNCT_RE.sub("", t)          # 中文逗号/句号/空白对设备指令无语义，全部去掉
    t = _PREFIX_RE.sub("", t)
    t = _TRAILING_RE.sub("", t)
    return t


def _target_of(m: re.Match) -> str:
    room = m.groupdict().get("room") or ""
    dev = m.groupdict().get("dev") or ""
    return f"{room}{dev}" if room else dev


def _fixed_target(m: re.Match, dev_word: str) -> str:
    """规则里设备词是字面量（无 dev 捕获组）时，用房间前缀 + 固定设备词构造 target。"""
    room = m.groupdict().get("room") or ""
    dev = m.groupdict().get("dev") or dev_word
    return f"{room}{dev}"


def _conf(base: float, m: re.Match | None = None) -> float:
    if m is not None and m.groupdict().get("room"):
        base += 0.05
    return min(round(base, 2), 0.99)


class _Rule:
    __slots__ = ("name", "regex", "build")

    def __init__(self, name: str, pattern: str, build):
        self.name = name
        self.regex = re.compile(pattern)
        self.build = build


# ---------------- 规则构建函数 ----------------

def _mk_simple(action: str, conf: float, params_builder=None):
    def build(m, _text):
        params = params_builder(m) if params_builder else []
        return DeviceCommand(target=_target_of(m), action=action,
                             params=params, confidence=_conf(conf, m))
    return build


def _build_temp(m, _text):
    temp = int(m.group("temp"))
    return DeviceCommand(target=_fixed_target(m, "空调"), action="set_temperature",
                         params=[temp], confidence=_conf(0.95, m))


def _build_ac_mode(m, _text):
    mode = _AC_MODE.get(m.group("mode"), m.group("mode"))
    return DeviceCommand(target=_fixed_target(m, "空调"), action="set_mode",
                         params=[mode], confidence=_conf(0.9, m))


def _build_fan_level(m, _text):
    raw = m.group("lvl")
    lvl = _CN_NUM.get(raw, None)
    if lvl is None:
        lvl = int(raw)
    return DeviceCommand(target=_fixed_target(m, "风扇"), action="set_fan_level",
                         params=[lvl], confidence=_conf(0.95, m))


def _build_osc(state: bool):
    def build(m, _text):
        return DeviceCommand(target=_fixed_target(m, "风扇"), action="set_oscillate",
                             params=[state], confidence=_conf(0.9, m))
    return build


def _build_brightness_abs(m, _text):
    br = max(1, min(100, int(m.group("br"))))
    return DeviceCommand(target=_target_of(m) or "灯", action="set_brightness",
                         params=[br], confidence=_conf(0.9, m))


def _build_brightness_rel(direction: str):
    def build(m, _text):
        return DeviceCommand(target=_target_of(m) or "灯", action=direction,
                             params=[10], confidence=_conf(0.85, m))
    return build


def _build_color(m, _text):
    rgb = _COLORS[m.group("color")]
    return DeviceCommand(target=_target_of(m) or "灯", action="set_color",
                         params=list(rgb), confidence=_conf(0.85, m))


def _build_sleep(m, text):
    if not ("关灯" in text or "灯关" in text):
        return None  # 只是「我要睡觉」之类，不算设备指令
    return DeviceCommand(target="灯", action="off", params=[], confidence=0.9)


def _build_all(action: str):
    def build(m, _text):
        dev = m.groupdict().get("devall") or "灯"
        return DeviceCommand(target=f"所有{dev}", action=action,
                             params=[], confidence=0.85)
    return build


# ---------------- 规则表（顺序即优先级，具体规则在前） ----------------

_RULES: list[_Rule] = [
    # 1-2 睡眠场景
    _Rule("sleep_off_1", r"(?:关灯|把灯关|灯关了?).*(?:睡觉|去睡|睡了)", _build_sleep),
    _Rule("sleep_off_2", r"(?:睡觉|要睡了|睡了|晚安)", _build_sleep),
    # 3-4 空调温度
    _Rule("ac_temp_set", rf"(?:把)?{_ROOM}{_DE}空调.*?"
          rf"(?:调到|调至|调为|调成|设定为?|设置为?)(?P<temp>\d{{1,2}})(?:度|℃|摄氏度)?",
          _build_temp),
    _Rule("ac_temp_direct", rf"(?:把)?{_ROOM}{_DE}空调(?:.*?)(?P<temp>\d{{1,2}})(?:度|℃|摄氏度)$",
          _build_temp),
    # 5 空调模式
    _Rule("ac_mode", rf"(?:把)?{_ROOM}{_DE}空调.*?(?P<mode>制冷|制热|除湿|送风|自动|节能|睡眠)(?:模式)?",
          _build_ac_mode),
    # 6-7 风扇档位
    _Rule("fan_level_1", rf"(?:把)?{_ROOM}{_DE}(?:风扇|电扇|循环扇|落地扇).*?"
          rf"(?P<lvl>一|二|两|三|四|五|[1-5])\s*档", _build_fan_level),
    _Rule("fan_level_2", rf"(?P<dev>风扇|电扇|循环扇|落地扇).*?开(?P<lvl>一|二|两|三|四|五|[1-5])档",
          _build_fan_level),
    # 8-9 风扇摇头
    _Rule("osc_off", rf"(?:把)?{_ROOM}{_DE}(?P<dev>风扇|电扇|循环扇|落地扇).*?"
          rf"(?:别|不要|关闭|关掉|停止|取消)(?:摇头|摆头)", _build_osc(False)),
    _Rule("osc_on", rf"(?:把)?{_ROOM}{_DE}(?P<dev>风扇|电扇|循环扇|落地扇).*?(?:摇头|摆头)",
          _build_osc(True)),
    # 10-11 亮度绝对值
    _Rule("brightness_abs", rf"(?:把)?{_ROOM}{_DE}(?P<dev>灯|台灯|吸顶灯|床头灯|吊灯|夜灯).*?"
          rf"亮度(?:调到|调至|调成|调到了|设为|设置为)?(?P<br>\d{{1,3}})%?",
          _build_brightness_abs),
    _Rule("brightness_abs_2", rf"(?:把)?{_ROOM}{_DE}(?P<dev>灯|台灯|吸顶灯|床头灯|吊灯|夜灯).*?"
          rf"(?:调到|调至|调成)(?P<br>\d{{1,3}})%?$", _build_brightness_abs),
    # 12-13 亮度相对调整
    _Rule("brightness_up", rf"(?:把)?{_ROOM}{_DE}(?P<dev>灯|台灯|吸顶灯|床头灯|吊灯|夜灯).*?"
          rf"(?:调亮|变亮|再亮|亮一点|亮一些|亮点|亮些)", _build_brightness_rel("brightness_up")),
    _Rule("brightness_down", rf"(?:把)?{_ROOM}{_DE}(?P<dev>灯|台灯|吸顶灯|床头灯|吊灯|夜灯).*?"
          rf"(?:调暗|变暗|再暗|暗一点|暗一些|暗点|暗些)", _build_brightness_rel("brightness_down")),
    # 14 颜色
    _Rule("light_color", rf"(?:把)?{_ROOM}{_DE}(?P<dev>灯|台灯|吸顶灯|床头灯|吊灯|夜灯).*?"
          rf"(?:调成|变成|变为|调到|换成)(?P<color>{_COLOR_WORDS})", _build_color),
    # 15-16 切换
    _Rule("toggle_1", rf"切换{_ROOM}{_DE}{_DEV}(?:的)?(?:状态|开关)?", _mk_simple("toggle", 0.75)),
    _Rule("toggle_2", rf"(?:把)?{_ROOM}{_DE}{_DEV}.*?(?:切换|切一下)(?:状态|开关)?",
          _mk_simple("toggle", 0.75)),
    # 17-18 全部设备
    _Rule("all_off", r"(?:把)?(?:所有|全部)(?:的)?(?P<devall>灯|设备|电器).*?(?:关闭|关掉|关上|关了|关)",
          _build_all("off")),
    _Rule("all_on", r"(?:打开|开启)(?:所有|全部)(?:的)?(?P<devall>灯|设备|电器)",
          _build_all("on")),
    # 19-21 打开
    _Rule("on_verb_first", rf"^(?:打开|开启)(?:一下)?{_ROOM}{_DE}{_DEV}(?:一下)?$",
          _mk_simple("on", 0.8)),
    _Rule("on_fused", rf"^开(?:一下)?{_ROOM}{_DE}{_DEV}$", _mk_simple("on", 0.8)),
    _Rule("on_target_first", rf"^(?:把)?{_ROOM}{_DE}{_DEV}(?:打开|开启|开一下|开)$",
          _mk_simple("on", 0.8)),
    # 22-24 关闭
    _Rule("off_verb_first", rf"^(?:关闭|关掉|关上)(?:一下)?{_ROOM}{_DE}{_DEV}(?:一下)?$",
          _mk_simple("off", 0.8)),
    _Rule("off_fused", rf"^关(?:一下)?{_ROOM}{_DE}{_DEV}(?:了)?$", _mk_simple("off", 0.8)),
    _Rule("off_target_first", rf"^(?:把)?{_ROOM}{_DE}{_DEV}(?:关闭|关掉|关上|关了|关一下|关)$",
          _mk_simple("off", 0.8)),
]


class IntentRouter:
    """规则 + 别名表的中文设备指令路由器。"""

    def __init__(self, mihome, alias_map: dict | None = None):
        self.mihome = mihome
        self.aliases: dict[str, str] = dict(alias_map or {})
        self._rules = _RULES

    def parse(self, text: str) -> DeviceCommand | None:
        """把中文指令解析成 DeviceCommand；未命中任何规则返回 None。"""
        t = _normalize(text)
        if not t:
            return None
        for rule in self._rules:
            m = rule.regex.search(t)
            if not m:
                continue
            try:
                cmd = rule.build(m, t)
            except Exception as exc:  # 单条规则异常不影响整体
                log.warning("规则 %s 处理 %r 出错：%s", rule.name, text, exc)
                continue
            if cmd is not None:
                log.info("意图命中[%s]：%r -> %s", rule.name, text, cmd)
                return cmd
        log.info("意图未命中：%r", text)
        return None

    def execute(self, cmd: DeviceCommand) -> dict:
        """执行指令：别名解析 → mihome.control。异常不外抛。"""
        if cmd is None:
            return {"ok": False, "error": "空指令"}
        base = {"target": cmd.target, "action": cmd.action, "params": list(cmd.params)}
        if self.mihome is None:
            log.warning("米家未启用，指令 %s 无法执行", cmd)
            return {"ok": False, "error": "米家未启用", **base}

        did = self.aliases.get(cmd.target)
        if not did:
            try:
                did = self.mihome.resolve(cmd.target)
            except Exception:
                did = cmd.target
        try:
            return self.mihome.control(did, cmd.action, list(cmd.params))
        except Exception as exc:  # mihome.control 契约上不抛，双保险
            log.error("执行设备指令失败：%s", exc)
            return {"ok": False, "error": str(exc), **base}
