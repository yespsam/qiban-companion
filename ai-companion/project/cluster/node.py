"""栖伴集群：节点信息与本机能力采集（SPEC §3.9）。

所有硬件探测均为「尽力而为」：任何一步失败都降级为安全默认值，
保证在无 GPU / 无 psutil / 受限容器环境下也能 import 并正常运行。
模块顶层只允许轻量 import（标准库 + core.logging_utils）。
"""
from __future__ import annotations

import os
import socket
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass

from core.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class NodeInfo:
    """集群节点信息（SPEC §3.9）。

    load: 0.0 ~ 1.0，越高越忙；last_heartbeat 为 Unix 时间戳，0 表示尚未心跳。
    """

    node_id: str
    role: str  # "master" | "worker"
    host: str
    port: int
    models: list[str]
    gpu_vram_mb: int
    load: float = 0.0
    last_heartbeat: float = 0.0

    def endpoint(self) -> str:
        """节点对外暴露的 OpenAI 兼容 HTTP 入口。"""
        return f"http://{self.host}:{self.port}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "NodeInfo":
        """从 JSON 字典还原；容忍缺字段与多余字段。"""
        if not isinstance(data, dict):
            raise TypeError(f"NodeInfo.from_dict 需要 dict，收到 {type(data).__name__}")
        return cls(
            node_id=str(data.get("node_id", "")),
            role=str(data.get("role", "worker")),
            host=str(data.get("host", "127.0.0.1")),
            port=int(data.get("port", 0) or 0),
            models=[str(m) for m in (data.get("models") or [])],
            gpu_vram_mb=int(data.get("gpu_vram_mb", 0) or 0),
            load=float(data.get("load", 0.0) or 0.0),
            last_heartbeat=float(data.get("last_heartbeat", 0.0) or 0.0),
        )


def collect_local_info(
    role: str = "worker",
    host: str | None = None,
    port: int = 8080,
    models: list[str] | None = None,
    node_id: str | None = None,
) -> NodeInfo:
    """采集本机能力并生成 NodeInfo。

    CPU / 内存 / 显存探测全部 try 包住：psutil 缺失、nvidia-smi 不存在、
    容器受限等情况下自动降级，绝不抛出异常。
    """
    if host is None:
        host = _local_ip()
    if node_id is None:
        node_id = _default_node_id()

    cpu_percent, mem_percent = _detect_cpu_mem()
    gpu_vram_mb = _detect_gpu_vram_mb()

    # 负载估计：取 CPU 与内存占用中较紧张的一方，钳制到 [0.0, 1.0]
    load = max(cpu_percent, mem_percent) / 100.0
    load = min(1.0, max(0.0, round(load, 3)))

    info = NodeInfo(
        node_id=node_id,
        role=role,
        host=host,
        port=port,
        models=list(models or []),
        gpu_vram_mb=gpu_vram_mb,
        load=load,
        last_heartbeat=time.time(),
    )
    logger.info(
        "本机能力采集完成: node_id=%s cpu=%.0f%% mem=%.0f%% gpu_vram=%dMB load=%.2f",
        info.node_id, cpu_percent, mem_percent, gpu_vram_mb, load,
    )
    return info


# ---------------------------------------------------------------------------
# 以下为尽力而为的探测 helpers，全部容忍失败
# ---------------------------------------------------------------------------

def _local_ip() -> str:
    """尽力获取本机局域网 IP，失败退回 127.0.0.1。"""
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    try:  # UDP 假连接 trick，不真正发包
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        pass
    return "127.0.0.1"


def _default_node_id() -> str:
    try:
        hostname = socket.gethostname() or "node"
    except OSError:
        hostname = "node"
    return f"{hostname}-{uuid.uuid4().hex[:6]}"


def _detect_cpu_mem() -> tuple[float, float]:
    """返回 (CPU 占用%, 内存占用%)。优先 psutil（懒加载），降级 os.getloadavg。"""
    try:
        import psutil  # 懒加载：可选依赖

        cpu = float(psutil.cpu_percent(interval=0.1))
        mem = float(psutil.virtual_memory().percent)
        return cpu, mem
    except Exception as exc:  # noqa: BLE001 —— 探测必须永不抛出
        logger.debug("psutil 不可用，CPU/内存探测降级: %s", exc)
    try:
        load1 = os.getloadavg()[0]
        ncpu = os.cpu_count() or 1
        return min(100.0, load1 / ncpu * 100.0), 0.0
    except (OSError, AttributeError):
        return 0.0, 0.0


def _detect_gpu_vram_mb() -> int:
    """尽力探测 GPU 显存总量（MB）。无 GPU / 无工具时返回 0。"""
    # 路径 1：pynvml（懒加载，可选依赖）
    try:
        import pynvml  # type: ignore  # 懒加载

        pynvml.nvmlInit()
        total = 0
        for i in range(pynvml.nvmlDeviceGetCount()):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            total += int(pynvml.nvmlDeviceGetMemoryInfo(handle).total)
        pynvml.nvmlShutdown()
        if total > 0:
            return total // (1024 * 1024)
    except Exception as exc:  # noqa: BLE001
        logger.debug("pynvml 显存探测失败，尝试 nvidia-smi: %s", exc)

    # 路径 2：nvidia-smi 命令行
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if out.returncode == 0:
            total = sum(int(line.strip()) for line in out.stdout.splitlines() if line.strip().isdigit())
            if total > 0:
                return total
    except Exception as exc:  # noqa: BLE001 —— FileNotFoundError/TimeoutExpired 等
        logger.debug("nvidia-smi 显存探测失败: %s", exc)

    return 0
