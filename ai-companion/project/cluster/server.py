"""栖伴集群：本地模型服务封装（SPEC §3.9）。

- ``llamacpp`` 后端：启动 llama.cpp 的 ``llama-server`` 子进程；
  二进制或模型文件缺失时抛出带安装/下载指引的 :class:`ClusterUnavailable`。
- ``ollama`` 后端：检测本地 Ollama 是否在运行；未运行且有二进制时拉起
  ``ollama serve``，否则给出安装指引。

settings 采用鸭子类型（任何带 llm_backend / model_id / data_dir 属性的对象），
与 ``core.config.Settings`` 解耦，保证本模块可独立导入与测试。
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from core.logging_utils import get_logger

from .router import ClusterUnavailable

if TYPE_CHECKING:  # 仅类型标注，避免运行时依赖 core 分支
    from core.config import Settings

logger = get_logger(__name__)

OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_PORT = 11434

_LLAMA_SERVER_GUIDE = """\
未找到 llama-server 二进制（llama.cpp 的 server 模式）。安装指引：
  - Windows/macOS/Linux：从 https://github.com/ggml-org/llama.cpp/releases 下载预编译包，
    解压后把 llama-server 加入 PATH；
  - macOS 也可用 `brew install llama.cpp`；Linux 可用发行版包管理器或源码编译
    （cmake -B build && cmake --build build --config Release -t llama-server）；
  - 或设置环境变量 HERMES_LLAMA_SERVER 指向 llama-server 的完整路径。
"""

_OLLAMA_GUIDE = """\
未检测到 Ollama。安装指引：
  - https://ollama.com/download 下载安装包；
  - Linux 可用 `curl -fsSL https://ollama.com/install.sh | sh`；
  - 安装后运行 `ollama serve`，并 `ollama pull <模型标签>`（如 hermes3:8b）。
"""


class ModelServer:
    """封装本地模型服务的启动 / 停止 / 入口地址。"""

    def __init__(self, settings: "Settings", models_yaml: str = "config/models.yaml"):
        self.settings = settings
        self.models_yaml = models_yaml
        self._proc: subprocess.Popen | None = None
        self._port: int | None = None
        self._base: str | None = None

    # ------------------------------------------------------------------ 公共接口

    def start(self, port: int = 0) -> int:
        """按 settings.llm_backend 启动模型服务，返回监听端口。

        :param port: 期望端口，0 表示自动分配（仅 llamacpp 生效；ollama 固定 11434）。
        """
        if self._proc is not None and self._port is not None:
            logger.info("模型服务已在运行: %s", self._base)
            return self._port
        backend = str(getattr(self.settings, "llm_backend", "llamacpp"))
        if backend == "ollama":
            return self._start_ollama()
        if backend == "llamacpp":
            return self._start_llamacpp(port)
        raise ClusterUnavailable(
            f"llm_backend={backend!r} 无需由 ModelServer 启动"
            "（mock 后端在进程内直接可用；如需真实模型请改用 llamacpp 或 ollama）"
        )

    def stop(self) -> None:
        """停止由本对象启动的子进程；重复调用安全。"""
        proc, self._proc = self._proc, None
        self._port, self._base = None, None
        if proc is None:
            return
        if proc.poll() is not None:
            return  # 已自行退出
        logger.info("停止模型服务 (pid=%s)", proc.pid)
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("模型服务进程 %s 未能正常结束", proc.pid)
        except OSError as exc:
            logger.warning("停止模型服务时出错: %s", exc)

    def endpoint(self) -> str:
        """服务的 OpenAI 兼容入口，如 http://127.0.0.1:8080；未启动时抛 RuntimeError。"""
        if not self._base:
            raise RuntimeError("模型服务尚未启动，请先调用 start()")
        return self._base

    def ollama_running(self, base_url: str = OLLAMA_BASE_URL) -> bool:
        """探测 Ollama 是否已在运行（短超时 HTTP 探测，任何异常都视为未运行）。"""
        try:
            resp = httpx.get(f"{base_url}/api/version", timeout=2.0)
            return resp.status_code == 200
        except Exception:  # noqa: BLE001 —— 探测必须永不抛出
            return False

    # ------------------------------------------------------------------ llamacpp

    def _start_llamacpp(self, port: int) -> int:
        binary = os.environ.get("HERMES_LLAMA_SERVER") or shutil.which("llama-server")
        if not binary:
            raise ClusterUnavailable(_LLAMA_SERVER_GUIDE)
        model_path = self._resolve_model_path()
        ctx = self._model_ctx()
        actual_port = port or _free_port()
        args = [
            binary,
            "--model", str(model_path),
            "--host", "127.0.0.1",
            "--port", str(actual_port),
            "--ctx-size", str(ctx),
        ]
        logger.info("启动 llama-server: %s", " ".join(args))
        try:
            self._proc = subprocess.Popen(args)
        except OSError as exc:
            raise ClusterUnavailable(f"llama-server 启动失败: {exc}\n{_LLAMA_SERVER_GUIDE}") from exc
        base = f"http://127.0.0.1:{actual_port}"
        self._wait_ready(f"{base}/v1/models", timeout=120.0)
        self._base, self._port = base, actual_port
        logger.info("llama-server 已就绪: %s", base)
        return actual_port

    def _resolve_model_path(self) -> Path:
        """按 models.yaml + settings.model_id 定位 GGUF 文件，缺失时给下载指引。"""
        model_id = str(getattr(self.settings, "model_id", ""))
        entry = self._model_entry(model_id)
        filename = entry.get("file", "")
        data_dir = Path(str(getattr(self.settings, "data_dir", "data")))
        candidates = [data_dir / "models" / filename, Path("models") / filename, Path(filename)]
        for cand in candidates:
            if filename and cand.exists():
                return cand
        repo = entry.get("repo", "<未知仓库>")
        raise ClusterUnavailable(
            f"模型文件缺失: 未找到 {filename!r}（已查找: "
            + ", ".join(str(c) for c in candidates)
            + f"）。下载指引：运行 `python installer/download_model.py --model {model_id}`，"
            f"或手动从 HuggingFace 仓库 {repo} 下载 {filename} 放到 {data_dir / 'models'}/。"
        )

    def _model_entry(self, model_id: str) -> dict:
        """读取 models.yaml 中指定模型的条目（yaml 懒加载）。"""
        try:
            import yaml  # 懒加载：pyyaml 为核心依赖，但仍保持按需导入
        except ImportError as exc:
            raise ClusterUnavailable("缺少 pyyaml，无法读取模型注册表：pip install pyyaml") from exc
        try:
            raw = yaml.safe_load(Path(self.models_yaml).read_text(encoding="utf-8")) or {}
        except OSError as exc:
            raise ClusterUnavailable(f"模型注册表读取失败: {self.models_yaml}: {exc}") from exc
        entry = (raw.get("models") or {}).get(model_id)
        if not isinstance(entry, dict):
            raise ClusterUnavailable(
                f"模型 {model_id!r} 未在 {self.models_yaml} 的 models 中注册"
            )
        return entry

    def _model_ctx(self) -> int:
        try:
            entry = self._model_entry(str(getattr(self.settings, "model_id", "")))
            return int(entry.get("ctx", 8192))
        except (ClusterUnavailable, TypeError, ValueError):
            return 8192

    # ------------------------------------------------------------------ ollama

    def _start_ollama(self) -> int:
        if self.ollama_running():
            logger.info("检测到 Ollama 已在运行: %s", OLLAMA_BASE_URL)
            self._base, self._port = OLLAMA_BASE_URL, OLLAMA_PORT
            return OLLAMA_PORT
        binary = shutil.which("ollama")
        if binary is None:
            raise ClusterUnavailable(_OLLAMA_GUIDE)
        logger.info("拉起 ollama serve ...")
        try:
            self._proc = subprocess.Popen(
                [binary, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise ClusterUnavailable(f"ollama serve 启动失败: {exc}\n{_OLLAMA_GUIDE}") from exc
        self._wait_ready(f"{OLLAMA_BASE_URL}/api/version", timeout=30.0)
        self._base, self._port = OLLAMA_BASE_URL, OLLAMA_PORT
        logger.info("Ollama 已就绪: %s", OLLAMA_BASE_URL)
        return OLLAMA_PORT

    # ------------------------------------------------------------------ 内部

    def _wait_ready(self, url: str, timeout: float) -> None:
        """轮询直到服务就绪；超时或子进程提前退出则抛 ClusterUnavailable。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc is not None and self._proc.poll() is not None:
                raise ClusterUnavailable(
                    f"模型服务进程提前退出（exit={self._proc.returncode}），"
                    "请检查模型文件与 llama-server/ollama 日志"
                )
            try:
                if httpx.get(url, timeout=2.0).status_code == 200:
                    return
            except Exception:  # noqa: BLE001 —— 未就绪属正常，继续等
                pass
            time.sleep(0.5)
        self.stop()
        raise ClusterUnavailable(f"模型服务在 {timeout:.0f}s 内未就绪: {url}")


def _free_port() -> int:
    """向操作系统申请一个空闲端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
