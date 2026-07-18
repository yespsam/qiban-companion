"""devices 模块：蓝牙 BLE + 米家智能家居 + 语音意图路由。

硬约束（SPEC §1）：bleak / miio / micloud 全部懒加载（仅在函数内 import），
本包顶层只导入轻量模块，无蓝牙 / 无米家依赖的环境可正常 import。
"""
from devices.bluetooth_manager import BTDevice, BluetoothManager
from devices.mihome import MiDevice, MiHome
from devices.intent import DeviceCommand, IntentRouter

__all__ = [
    "BTDevice",
    "BluetoothManager",
    "MiDevice",
    "MiHome",
    "DeviceCommand",
    "IntentRouter",
]
