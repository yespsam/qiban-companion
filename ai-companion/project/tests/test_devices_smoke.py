"""devices 模块冒烟测试（SPEC §6）。

在无蓝牙 / 无米家依赖（bleak、python-miio、micloud 全部不可用）的环境下验证：
- 模块可正常 import（懒加载铁律：顶层无重依赖 import）
- MiHome.discover() 依赖缺失时返回空列表并记日志
- MiHome.control() / status() 返回 {"ok": False, ...} 而不抛异常
- BluetoothManager 各操作安全降级、持久化可读
- audio_route 在任何平台上都不抛异常
"""
from __future__ import annotations

import asyncio
import builtins
import json
import logging
import sys

import pytest


@pytest.fixture()
def no_heavy_deps(monkeypatch):
    """无论 venv 里是否真的装了重依赖，都模拟「依赖缺失」环境。"""
    blocked = {"miio", "micloud", "bleak"}
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.split(".")[0] in blocked:
            raise ImportError(f"blocked in test: {name}")
        return real_import(name, *args, **kwargs)

    for mod in list(sys.modules):
        if mod.split(".")[0] in blocked:
            monkeypatch.delitem(sys.modules, mod, raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    yield


# ---------------- import 冒烟 ----------------

def test_modules_importable():
    import devices  # noqa: F401
    import devices.audio_route  # noqa: F401
    import devices.bluetooth_manager  # noqa: F401
    import devices.intent  # noqa: F401
    import devices.mihome  # noqa: F401
    from devices import BluetoothManager, IntentRouter, MiHome  # noqa: F401


def test_no_heavy_import_at_top_level():
    import devices  # noqa: F401

    for heavy in ("bleak", "miio", "micloud"):
        assert heavy not in sys.modules, f"{heavy} 不应在 import devices 时加载"


# ---------------- MiHome 降级行为 ----------------

def test_mihome_discover_lan_no_deps(no_heavy_deps, tmp_path, caplog):
    from devices.mihome import MiHome

    mh = MiHome(mode="lan", cfg_path=str(tmp_path / "mihome_devices.json"))
    with caplog.at_level(logging.WARNING, logger="devices.mihome"):
        devices = mh.discover()
    assert devices == []
    assert any("python-miio" in r.message for r in caplog.records)


def test_mihome_discover_cloud_no_deps(no_heavy_deps, tmp_path, caplog):
    from devices.mihome import MiHome

    mh = MiHome(
        mode="cloud",
        cfg_path=str(tmp_path / "mihome_devices.json"),
        cloud_user="u",
        cloud_password="p",
    )
    with caplog.at_level(logging.WARNING, logger="devices.mihome"):
        devices = mh.discover()
    assert devices == []
    assert any("micloud" in r.message for r in caplog.records)


def test_mihome_discover_cloud_no_credentials(no_heavy_deps, tmp_path, caplog, monkeypatch):
    from devices.mihome import MiHome

    monkeypatch.delenv("MIHOME_USER", raising=False)
    monkeypatch.delenv("MIHOME_PASSWORD", raising=False)
    mh = MiHome(mode="cloud", cfg_path=str(tmp_path / "mihome_devices.json"))
    with caplog.at_level(logging.WARNING, logger="devices.mihome"):
        assert mh.discover() == []
    assert any("账号" in r.message for r in caplog.records)


def test_mihome_control_unknown_device(no_heavy_deps, tmp_path):
    from devices.mihome import MiHome

    mh = MiHome(cfg_path=str(tmp_path / "mihome_devices.json"))
    result = mh.control("nonexistent", "on")
    assert result["ok"] is False
    assert "error" in result


def test_mihome_control_no_deps(no_heavy_deps, tmp_path):
    from devices.mihome import MiHome

    cfg = tmp_path / "mihome_devices.json"
    cfg.write_text(
        json.dumps({"devices": [{"did": "1", "name": "灯", "model": "m",
                                 "ip": "192.168.1.2", "token": "t", "online": True}]}),
        encoding="utf-8",
    )
    mh = MiHome(cfg_path=str(cfg))
    result = mh.control("1", "on")
    assert result["ok"] is False
    assert "python-miio" in result["error"]


def test_mihome_status_no_deps(no_heavy_deps, tmp_path):
    from devices.mihome import MiHome

    mh = MiHome(cfg_path=str(tmp_path / "mihome_devices.json"))
    assert mh.status("nonexistent")["ok"] is False


def test_mihome_cache_roundtrip_and_resolve(no_heavy_deps, tmp_path):
    from devices.mihome import MiDevice, MiHome

    mh = MiHome(cfg_path=str(tmp_path / "mihome_devices.json"))
    mh.add_device(did="62100441", name="客厅灯", model="yeelink.light", ip="192.168.1.10", token="t" * 32)
    devices = mh.list_devices()
    assert len(devices) == 1
    assert isinstance(devices[0], MiDevice)
    assert mh.get_device("62100441").name == "客厅灯"
    assert mh.resolve("客厅灯") == "62100441"
    assert mh.resolve("不存在的设备") == "不存在的设备"


# ---------------- BluetoothManager 降级行为 ----------------

def test_bluetooth_list_saved_empty(tmp_path):
    from devices.bluetooth_manager import BluetoothManager

    mgr = BluetoothManager(persist_path=str(tmp_path / "bluetooth.json"))
    assert mgr.list_saved() == []


def test_bluetooth_scan_no_bleak(no_heavy_deps, tmp_path):
    from devices.bluetooth_manager import BluetoothManager

    mgr = BluetoothManager(persist_path=str(tmp_path / "bluetooth.json"))
    assert asyncio.run(mgr.scan(timeout=0.1)) == []
    assert mgr.scan_sync(timeout=0.1) == []


def test_bluetooth_pair_connect_no_bleak(no_heavy_deps, tmp_path):
    from devices.bluetooth_manager import BluetoothManager

    mgr = BluetoothManager(persist_path=str(tmp_path / "bluetooth.json"))
    assert mgr.pair_sync("AA:BB:CC:DD:EE:FF") is False
    assert mgr.connect_sync("AA:BB:CC:DD:EE:FF") is False


def test_bluetooth_saved_roundtrip(tmp_path):
    from devices.bluetooth_manager import BTDevice, BluetoothManager

    path = tmp_path / "bluetooth.json"
    path.write_text(
        json.dumps({"devices": [{"name": "耳机", "address": "AA:BB", "rssi": -50, "paired": True}]}),
        encoding="utf-8",
    )
    mgr = BluetoothManager(persist_path=str(path))
    saved = mgr.list_saved()
    assert saved == [BTDevice(name="耳机", address="AA:BB", rssi=-50, paired=True)]


# ---------------- 音频路由 ----------------

def test_audio_route_never_raises():
    from devices import audio_route

    result = audio_route.route_to_bluetooth("不存在的蓝牙设备xyz")
    assert isinstance(result, bool)  # 找不到设备/工具时 False，但绝不抛异常


def test_audio_route_pick_linux_sink():
    from devices.audio_route import _pick_linux_sink

    output = "0\talsa_output.pci.analog\tmodule-alsa-card\ts16le\tSUSPENDED\n" \
             "1\tbluez_sink.aa_bb_cc.a2dp-sink\tmodule-bluez5\tS16LE\tRUNNING\n"
    assert _pick_linux_sink(output, None) == "bluez_sink.aa_bb_cc.a2dp-sink"
    assert _pick_linux_sink(output, "analog") == "alsa_output.pci.analog"
    assert _pick_linux_sink(output, "不存在") is None
    assert _pick_linux_sink("0\talsa_output.pci.analog\tx\ty\tz\n", None) is None


# ---------------- IntentRouter 冒烟 ----------------

def test_intent_router_smoke():
    from devices import IntentRouter

    router = IntentRouter(None)
    assert router.parse("把客厅的灯打开") is not None
    assert router.parse("今天天气怎么样") is None
