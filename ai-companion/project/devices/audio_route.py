"""蓝牙音频路由（SPEC §2 devices/audio_route.py）。

按平台（Windows / macOS / Linux）用系统命令「尽力而为」地把默认音频输出
切换到已连接的蓝牙设备：
- Linux  ：pactl（PulseAudio / PipeWire 兼容层）列出 sink，匹配 bluez/bluetooth/设备名
- macOS  ：SwitchAudioSource（brew install switchaudio-osx），缺失时降级返回 False
- Windows：优先 nircmd（setdefaultsounddevice），其次 PowerShell AudioDeviceCmdlets 模块

所有外部调用都有超时与异常兜底；任何失败只记日志并返回 False，绝不外抛。
本模块只使用标准库，无重依赖。
"""
from __future__ import annotations

import platform
import shutil
import subprocess

try:
    from core.logging_utils import get_logger
except Exception:  # pragma: no cover - 兜底
    import logging

    def get_logger(name: str) -> "logging.Logger":
        return logging.getLogger(name)


log = get_logger("devices.audio_route")

_CMD_TIMEOUT = 8.0


def _run(cmd: list[str], timeout: float = _CMD_TIMEOUT) -> tuple[bool, str]:
    """执行系统命令，返回 (是否成功, 合并输出)。任何异常都转为 (False, 错误)。"""
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    except Exception as exc:  # FileNotFoundError / TimeoutExpired / OSError ...
        return False, str(exc)


def route_to_bluetooth(device_name: str | None = None) -> bool:
    """把系统默认音频输出切到蓝牙设备。

    device_name: 目标输出设备名（子串匹配，大小写不敏感）；为 None 时匹配
    任意蓝牙音频输出（bluez / bluetooth 关键字）。
    返回是否切换成功。不支持的平台 / 缺少工具 / 未找到设备都返回 False。
    """
    system = platform.system()
    try:
        if system == "Linux":
            return _route_linux(device_name)
        if system == "Darwin":
            return _route_macos(device_name)
        if system == "Windows":
            return _route_windows(device_name)
        log.warning("不支持的平台 %s，音频路由跳过", system)
        return False
    except Exception as exc:  # 双保险：任何意外都不外抛
        log.error("音频路由异常：%s", exc)
        return False


# ---------------- Linux ----------------

def _pick_linux_sink(short_sinks_output: str, device_name: str | None) -> str | None:
    """从 `pactl list short sinks` 输出里挑一个蓝牙 sink 名。"""
    needle = (device_name or "").lower()
    for line in short_sinks_output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t") if "\t" in line else line.split()
        if len(parts) < 2:
            continue
        sink = parts[1]
        low = sink.lower()
        if needle and needle in low:
            return sink
        if not needle and ("bluez" in low or "bluetooth" in low or "a2dp" in low):
            return sink
    return None


def _route_linux(device_name: str | None) -> bool:
    if not shutil.which("pactl"):
        log.warning("未找到 pactl（PulseAudio/PipeWire），无法切换音频输出")
        return False
    ok, out = _run(["pactl", "list", "short", "sinks"])
    if not ok:
        log.error("pactl 列出音频输出失败：%s", out.strip())
        return False
    sink = _pick_linux_sink(out, device_name)
    if not sink:
        log.info("未找到蓝牙音频输出（device_name=%s）", device_name)
        return False
    ok, out = _run(["pactl", "set-default-sink", sink])
    if not ok:
        log.error("设置默认输出 %s 失败：%s", sink, out.strip())
        return False
    # 尽力把已存在的播放流也迁到新 sink（失败不影响结果）
    ok_inputs, inputs = _run(["pactl", "list", "short", "sink-inputs"])
    if ok_inputs:
        for line in inputs.splitlines():
            parts = line.split("\t") if "\t" in line else line.split()
            if parts and parts[0].isdigit():
                _run(["pactl", "move-sink-input", parts[0], sink])
    log.info("默认音频输出已切换到 %s", sink)
    return True


# ---------------- macOS ----------------

def _route_macos(device_name: str | None) -> bool:
    exe = shutil.which("SwitchAudioSource")
    if not exe:
        log.warning("未找到 SwitchAudioSource，请先 `brew install switchaudio-osx`；音频路由跳过")
        return False
    ok, out = _run([exe, "-a"])
    if not ok:
        log.error("列出音频输出失败：%s", out.strip())
        return False
    needle = (device_name or "").lower()
    target = None
    for line in out.splitlines():
        name = line.strip()
        if not name:
            continue
        low = name.lower()
        if needle and needle in low:
            target = name
            break
        if not needle and ("bluetooth" in low or "airpods" in low or "bt " in low):
            target = name
            break
    if not target:
        log.info("未找到蓝牙音频输出（device_name=%s）", device_name)
        return False
    ok, out = _run([exe, "-s", target])
    if ok:
        log.info("默认音频输出已切换到 %s", target)
    else:
        log.error("切换音频输出到 %s 失败：%s", target, out.strip())
    return ok


# ---------------- Windows ----------------

def _route_windows(device_name: str | None) -> bool:
    # 方案 1：nircmd（需要明确设备名）
    nircmd = shutil.which("nircmd") or shutil.which("nircmd.exe")
    if nircmd and device_name:
        ok, out = _run([nircmd, "setdefaultsounddevice", device_name])
        if ok:
            log.info("默认音频输出已切换到 %s", device_name)
            return True
        log.warning("nircmd 切换失败：%s，尝试 PowerShell 方案", out.strip())

    # 方案 2：PowerShell + AudioDeviceCmdlets 模块
    powershell = shutil.which("powershell") or shutil.which("powershell.exe") or shutil.which("pwsh")
    if not powershell:
        log.warning("Windows 音频路由需要 nircmd 或 PowerShell(AudioDeviceCmdlets)，均不可用")
        return False
    match = device_name or "bluetooth|bt |headphone|headset"
    script = (
        "$d = Get-AudioDevice -List | Where-Object "
        "{ $_.Type -eq 'Playback' -and $_.Name -match '" + match.replace("'", "''") + "' } "
        "| Select-Object -First 1; "
        "if ($d) { $d | Set-AudioDevice | Out-Null; exit 0 } else { exit 3 }"
    )
    ok, out = _run([powershell, "-NoProfile", "-NonInteractive", "-Command", script], timeout=20.0)
    if ok:
        log.info("默认音频输出已通过 PowerShell 切换（match=%s）", match)
        return True
    log.warning(
        "PowerShell 音频切换失败（%s）。可安装 AudioDeviceCmdlets："
        "Install-Module -Name AudioDeviceCmdlets",
        out.strip()[:200],
    )
    return False
