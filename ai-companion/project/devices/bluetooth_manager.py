"""蓝牙 BLE 管理器（SPEC §3.8）。

硬约束：bleak 只在函数内部 import（懒加载铁律），本模块顶层仅轻量 import，
无蓝牙硬件 / 未安装 bleak 的环境可正常 import 本模块。

- scan/pair/connect 为异步实现，另提供 *_sync 同步包装供 UI 使用。
- 已配对设备持久化到 data/bluetooth.json（可用环境变量 HERMES_HOME 覆盖项目根）。
- 所有硬件相关异常不外抛：失败记日志并返回 False / []。
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

try:  # 统一日志（core 由主代理提供）；core 不可用时降级标准 logging
    from core.logging_utils import get_logger
except Exception:  # pragma: no cover - 兜底
    import logging

    def get_logger(name: str) -> "logging.Logger":
        return logging.getLogger(name)


log = get_logger("devices.bluetooth")


@dataclass
class BTDevice:
    name: str
    address: str
    rssi: int = 0
    paired: bool = False


def _data_dir() -> Path:
    """运行时数据目录：<项目根>/data（HERMES_HOME 可覆盖项目根）。"""
    base = os.environ.get("HERMES_HOME")
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    d = root / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _run_sync(coro):
    """同步包装：无事件循环时直接 asyncio.run；已有事件循环（如 UI/语音协程）
    时放到独立线程里跑一个新 loop，避免 'asyncio.run() cannot be called
    from a running event loop'。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # noqa: BLE001 - 需要透传给调用方
            result["error"] = exc

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


class BluetoothManager:
    """BLE 扫描 / 配对 / 连接管理（bleak 懒加载）。"""

    def __init__(self, persist_path: str | None = None):
        # persist_path 仅供测试注入；默认 data/bluetooth.json
        self._path = Path(persist_path) if persist_path else _data_dir() / "bluetooth.json"
        self._last_scan: dict[str, BTDevice] = {}  # address -> 最近一次扫描结果

    # ---------------- 异步 API（SPEC §3.8） ----------------

    async def scan(self, timeout: float = 8.0) -> list[BTDevice]:
        """扫描附近 BLE 设备。bleak 缺失/无适配器时记日志并返回 []。"""
        try:
            from bleak import BleakScanner  # 懒加载
        except Exception as exc:  # ImportError 等
            log.warning("bleak 不可用（%s），蓝牙扫描跳过", exc)
            return []

        devices: list[BTDevice] = []
        try:
            try:
                # bleak >= 0.19 推荐 return_adv=True 以获取 RSSI
                found = await BleakScanner.discover(timeout=timeout, return_adv=True)
                for address, (dev, adv) in (found or {}).items():
                    devices.append(
                        BTDevice(
                            name=dev.name or (getattr(adv, "local_name", "") or ""),
                            address=address or dev.address,
                            rssi=int(getattr(adv, "rssi", 0) or 0),
                        )
                    )
            except TypeError:
                # 旧版 bleak：无 return_adv 参数
                for dev in await BleakScanner.discover(timeout=timeout):
                    devices.append(
                        BTDevice(
                            name=dev.name or "",
                            address=dev.address,
                            rssi=int(getattr(dev, "rssi", 0) or 0),
                        )
                    )
        except Exception as exc:  # 无适配器 / 权限不足 / 平台不支持
            log.error("蓝牙扫描失败：%s", exc)
            return []

        saved = {d.address for d in self.list_saved()}
        for d in devices:
            d.paired = d.address in saved
            if d.address:
                self._last_scan[d.address] = d
        devices.sort(key=lambda d: d.rssi, reverse=True)
        log.info("蓝牙扫描完成，发现 %d 台设备", len(devices))
        return devices

    async def pair(self, address: str) -> bool:
        """配对指定地址设备，成功后写入 data/bluetooth.json。"""
        try:
            from bleak import BleakClient  # 懒加载
        except Exception as exc:
            log.warning("bleak 不可用（%s），无法配对 %s", exc, address)
            return False

        try:
            async with BleakClient(address) as client:
                try:
                    paired = await client.pair()
                except AttributeError:  # 极旧 bleak 无 pair()
                    paired = getattr(client, "is_connected", False)
                ok = bool(paired) if paired is not None else True
        except Exception as exc:
            log.error("配对 %s 失败：%s", address, exc)
            return False

        if ok:
            known = self._last_scan.get(address)
            self._save(BTDevice(name=(known.name if known else ""), address=address, paired=True))
            log.info("配对成功：%s", address)
        else:
            log.warning("配对 %s 未成功", address)
        return ok

    async def connect(self, address: str) -> bool:
        """连接指定地址设备（验证可连接后即断开，保持轻量）。
        音频输出切换请配合 devices.audio_route.route_to_bluetooth 使用。"""
        try:
            from bleak import BleakClient  # 懒加载
        except Exception as exc:
            log.warning("bleak 不可用（%s），无法连接 %s", exc, address)
            return False

        try:
            async with BleakClient(address) as client:
                ok = bool(getattr(client, "is_connected", True))
        except Exception as exc:
            log.error("连接 %s 失败：%s", address, exc)
            return False

        if ok:
            known = self._last_scan.get(address)
            old = {d.address: d for d in self.list_saved()}.get(address)
            self._save(
                BTDevice(
                    name=(known.name if known else (old.name if old else "")),
                    address=address,
                    paired=bool(old.paired) if old else False,
                )
            )
            log.info("连接成功：%s", address)
        return ok

    # ---------------- 同步包装（供 UI 调用） ----------------

    def scan_sync(self, timeout: float = 8.0) -> list[BTDevice]:
        return _run_sync(self.scan(timeout))

    def pair_sync(self, address: str) -> bool:
        return _run_sync(self.pair(address))

    def connect_sync(self, address: str) -> bool:
        return _run_sync(self.connect(address))

    # ---------------- 持久化 ----------------

    def list_saved(self) -> list[BTDevice]:
        """读取 data/bluetooth.json 中已保存（配对过）的设备。"""
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except Exception as exc:
            log.error("读取 %s 失败：%s", self._path, exc)
            return []
        items = raw.get("devices", raw) if isinstance(raw, dict) else raw
        out: list[BTDevice] = []
        for it in items or []:
            try:
                out.append(
                    BTDevice(
                        name=str(it.get("name", "")),
                        address=str(it.get("address", "")),
                        rssi=int(it.get("rssi", 0) or 0),
                        paired=bool(it.get("paired", False)),
                    )
                )
            except Exception as exc:  # 单条坏数据不拖垮整体
                log.warning("跳过损坏的蓝牙设备记录：%s (%s)", it, exc)
        return out

    def _save(self, device: BTDevice) -> None:
        """按 address upsert 一条设备记录。"""
        devices = {d.address: d for d in self.list_saved()}
        devices[device.address] = device
        payload = {"devices": [asdict(d) for d in devices.values() if d.address]}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            log.error("写入 %s 失败：%s", self._path, exc)
