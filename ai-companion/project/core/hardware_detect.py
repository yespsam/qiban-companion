"""硬件自检（SPEC §2）：检测 CPU / 内存 / 显存，推荐 lite/standard/pro 档位。

所有探测手段都被 try 包住：无 GPU、无 nvidia-smi、非主流平台时也能安全返回
部分信息（缺失项为 0/空字符串）。本模块只依赖标准库 + core.config（懒 import）。

用法：
    python core/hardware_detect.py            # 打印检测结果与档位建议
    python core/hardware_detect.py --write    # 并把建议档位写入 config/settings.yaml
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys

# 推荐阈值（MB）
_PRO_VRAM_MB = 16_000       # 16GB+ 显存 → pro
_STANDARD_VRAM_MB = 8_000   # 8GB 显存 → standard
_STANDARD_CPU_RAM_MB = 16_384   # 纯 CPU 跑 8B Q4 的最低舒适内存
_STANDARD_CPU_CORES = 8


def _detect_ram_mb() -> int:
    """跨平台物理内存检测；任一步失败返回 0。"""
    system = platform.system()
    if system == "Linux":
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024  # kB → MB
    elif system == "Darwin":
        out = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return int(out.stdout.strip()) // (1024 * 1024)
    elif system == "Windows":
        import ctypes

        class _MEMSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = _MEMSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return stat.ullTotalPhys // (1024 * 1024)
    return 0


def _detect_gpu() -> tuple[str, int]:
    """返回 (gpu_name, vram_mb)。优先 nvidia-smi；macOS 走 system_profiler。"""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            names, vrams = [], []
            for line in out.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 2:
                    names.append(parts[0])
                    try:
                        vrams.append(int(float(parts[1])))
                    except ValueError:
                        pass
            if vrams:
                return " + ".join(names), max(vrams)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass

    if platform.system() == "Darwin":
        try:
            out = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=15,
            )
            if out.returncode == 0:
                name, vram = "", 0
                for line in out.stdout.splitlines():
                    line = line.strip()
                    if line.startswith("Chipset Model:") and not name:
                        name = line.split(":", 1)[1].strip()
                    m = re.search(r"VRAM[^:]*:\s*(\d+)\s*(MB|GB)", line)
                    if m:
                        size = int(m.group(1)) * (1024 if m.group(2) == "GB" else 1)
                        vram = max(vram, size)
                if name or vram:
                    return name, vram
        except (OSError, subprocess.SubprocessError):
            pass
    return "", 0


def detect() -> dict:
    """检测硬件信息；所有步骤容错，绝不抛异常。"""
    info: dict = {
        "platform": platform.system().lower() or "unknown",
        "cpu_count": 0,
        "ram_mb": 0,
        "gpu_name": "",
        "gpu_vram_mb": 0,
    }
    try:
        info["cpu_count"] = os.cpu_count() or 0
    except Exception:  # noqa: BLE001 - 硬约束：检测必须容错
        pass
    try:
        info["ram_mb"] = _detect_ram_mb()
    except Exception:  # noqa: BLE001
        pass
    try:
        info["gpu_name"], info["gpu_vram_mb"] = _detect_gpu()
    except Exception:  # noqa: BLE001
        pass
    return info


def recommend_tier(info: dict) -> str:
    """按硬件信息推荐档位：lite | standard | pro。"""
    vram = int(info.get("gpu_vram_mb") or 0)
    ram = int(info.get("ram_mb") or 0)
    cpu = int(info.get("cpu_count") or 0)
    if vram >= _PRO_VRAM_MB:
        return "pro"
    if vram >= _STANDARD_VRAM_MB:
        return "standard"
    # 纯 CPU：内存与核数足够时可跑 standard（8B Q4 CPU 推理）
    if ram >= _STANDARD_CPU_RAM_MB and cpu >= _STANDARD_CPU_CORES:
        return "standard"
    return "lite"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    info = detect()
    tier = recommend_tier(info)
    print("=== 栖伴 硬件自检 ===")
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print(f"推荐档位: {tier}  (lite=CPU/树莓派, standard=8GB显存, pro=16GB+显存)")
    if "--write" in argv:
        from core.config import load_settings, save_settings  # 懒加载

        path = "config/settings.yaml"
        settings = load_settings(path)
        settings.tier = tier
        save_settings(settings, path)
        print(f"已写入 {path}: tier={tier}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
