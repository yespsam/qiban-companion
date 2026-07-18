"""IntentRouter 测试（SPEC §6：至少 12 条指令用例，含未命中场景）。

mihome 用 fake 对象，不依赖任何真实硬件/网络/重依赖。
"""
from __future__ import annotations

import pytest

from devices.intent import DeviceCommand, IntentRouter


class FakeMiHome:
    """记录 control 调用并返回成功。"""

    def __init__(self, resolvable: dict[str, str] | None = None):
        self.calls: list[tuple[str, str, list]] = []
        self._resolvable = resolvable or {}

    def resolve(self, name_or_did: str) -> str:
        return self._resolvable.get(name_or_did, name_or_did)

    def control(self, did: str, action: str, params: list | None = None) -> dict:
        params = list(params or [])
        self.calls.append((did, action, params))
        return {"ok": True, "did": did, "action": action, "params": params}


@pytest.fixture()
def fake():
    return FakeMiHome()


@pytest.fixture()
def router(fake):
    return IntentRouter(fake)


# ---------------- 开/关 ----------------

@pytest.mark.parametrize(
    "text, target, action",
    [
        ("把客厅的灯打开", "客厅灯", "on"),
        ("打开卧室空调", "卧室空调", "on"),
        ("开灯", "灯", "on"),
        ("空调打开", "空调", "on"),
        ("关灯", "灯", "off"),
        ("把书房台灯关了", "书房台灯", "off"),
        ("关闭客厅风扇", "客厅风扇", "off"),
        ("把加湿器打开", "加湿器", "on"),
        ("帮我把卧室的灯打开", "卧室灯", "on"),
        ("请打开厨房的灯", "厨房灯", "on"),
        ("小栖，关灯", "灯", "off"),
        ("给我开一下书房的台灯", "书房台灯", "on"),
        ("把客厅的灯打开吧", "客厅灯", "on"),
    ],
)
def test_on_off(router, text, target, action):
    cmd = router.parse(text)
    assert cmd is not None, f"未命中: {text}"
    assert cmd.target == target
    assert cmd.action == action
    assert cmd.params == []
    assert 0.0 < cmd.confidence <= 1.0


# ---------------- 温度 / 模式 / 档位 / 摇头 ----------------

@pytest.mark.parametrize(
    "text, action, params",
    [
        ("空调调到26度", "set_temperature", [26]),
        ("把空调温度调到24摄氏度", "set_temperature", [24]),
        ("卧室空调调到28", "set_temperature", [28]),
        ("空调调到制冷模式", "set_mode", ["cool"]),
        ("空调制热", "set_mode", ["heat"]),
        ("风扇开一档", "set_fan_level", [1]),
        ("把客厅风扇调到三档", "set_fan_level", [3]),
        ("电扇调到2档", "set_fan_level", [2]),
        ("风扇打开摇头", "set_oscillate", [True]),
        ("风扇别摇头", "set_oscillate", [False]),
    ],
)
def test_climate_and_fan(router, text, action, params):
    cmd = router.parse(text)
    assert cmd is not None, f"未命中: {text}"
    assert cmd.action == action
    assert cmd.params == params


@pytest.mark.parametrize(
    "text, target, action, params",
    [
        ("麻烦你把卧室空调调到26度", "卧室空调", "set_temperature", [26]),
        ("把客厅空调设定为25摄氏度", "客厅空调", "set_temperature", [25]),
        ("卧室空调制热", "卧室空调", "set_mode", ["heat"]),
        ("把客厅风扇调到二档", "客厅风扇", "set_fan_level", [2]),
        ("卧室风扇别摇头", "卧室风扇", "set_oscillate", [False]),
    ],
)
def test_target_keeps_room_prefix(router, text, target, action, params):
    cmd = router.parse(text)
    assert cmd is not None, f"未命中: {text}"
    assert cmd.target == target
    assert cmd.action == action
    assert cmd.params == params


# ---------------- 亮度 / 颜色 / 场景 / 切换 ----------------

@pytest.mark.parametrize(
    "text, target, action, params",
    [
        ("灯调亮点", "灯", "brightness_up", [10]),
        ("把卧室的灯调暗一点", "卧室灯", "brightness_down", [10]),
        ("把灯亮度调到50", "灯", "set_brightness", [50]),
        ("台灯调到80", "台灯", "set_brightness", [80]),
        ("把灯调成暖黄色", "灯", "set_color", [255, 223, 178]),
        ("把客厅的灯变成红色", "客厅灯", "set_color", [255, 0, 0]),
        ("关灯睡觉", "灯", "off", []),
        ("我要睡了把灯关了", "灯", "off", []),
        ("把所有灯都关了", "所有灯", "off", []),
        ("打开所有灯", "所有灯", "on", []),
        ("切换客厅灯状态", "客厅灯", "toggle", []),
    ],
)
def test_light_scene_toggle(router, text, target, action, params):
    cmd = router.parse(text)
    assert cmd is not None, f"未命中: {text}"
    assert cmd.target == target
    assert cmd.action == action
    assert cmd.params == params


# ---------------- 未命中 ----------------

@pytest.mark.parametrize(
    "text",
    [
        "今天天气怎么样",
        "给我讲个笑话",
        "我想你了",
        "现在几点了",
        "我要睡觉了",          # 无「关灯」语义，不算设备指令
        "",
        "   ",
    ],
)
def test_no_match(router, text):
    assert router.parse(text) is None


# ---------------- execute ----------------

def test_execute_calls_mihome(router, fake):
    cmd = router.parse("把客厅的灯打开")
    result = router.execute(cmd)
    assert result["ok"] is True
    assert fake.calls == [("客厅灯", "on", [])]


def test_execute_alias_map(fake):
    router = IntentRouter(fake, alias_map={"客厅灯": "62100441"})
    cmd = router.parse("把客厅的灯打开")
    result = router.execute(cmd)
    assert result["ok"] is True
    assert result["did"] == "62100441"
    assert fake.calls[0][0] == "62100441"


def test_execute_resolve_via_mihome():
    fake = FakeMiHome(resolvable={"卧室空调": "987654"})
    router = IntentRouter(fake)
    result = router.execute(router.parse("打开卧室空调"))
    assert result["ok"] is True
    assert fake.calls[0] == ("987654", "on", [])


def test_execute_without_mihome():
    router = IntentRouter(None)
    cmd = router.parse("开灯")
    assert cmd is not None
    result = router.execute(cmd)
    assert result["ok"] is False
    assert "error" in result


def test_execute_none_command(router):
    assert router.execute(None)["ok"] is False


def test_execute_mihome_exception_swallowed():
    class BoomMiHome(FakeMiHome):
        def control(self, did, action, params=None):
            raise RuntimeError("boom")

    router = IntentRouter(BoomMiHome())
    result = router.execute(DeviceCommand(target="灯", action="on", params=[], confidence=0.9))
    assert result["ok"] is False
    assert "boom" in result["error"]
