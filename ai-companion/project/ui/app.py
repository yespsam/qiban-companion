"""FastAPI 应用装配（SPEC §3.10）。

``create_app(settings) -> FastAPI``：

- core（人格/记忆/情绪/引擎）**必装**：core 包 import 失败直接抛出；
  运行时装配失败（如 LLM 后端不可用）优雅降级为 ``engine=None``，
  聊天端点返回 503 / WS 错误帧，控制台其余部分照常可用。
- voice / devices / cluster 按 settings 开关懒装配，任何失败都不影响启动，
  对应端点返回 ``{"enabled": false, "error": ...}``。
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _log() -> logging.Logger:
    """优先使用 core.logging_utils.get_logger；core 缺席时退回标准 logging。"""
    try:
        from core.logging_utils import get_logger

        return get_logger("ui")
    except Exception:  # pragma: no cover - core 未合并时的兜底
        return logging.getLogger("ui")


class HermesState:
    """控制台共享状态：settings + 各子系统句柄（懒装配、可降级）。"""

    def __init__(self, settings):
        self.settings = settings
        # core
        self.engine = None
        self.engine_error: str = ""
        self.persona_manager = None
        self.persona_error: str = ""
        self.emotion = None
        self.emotion_error: str = ""
        # voice
        self.voice = None
        self.voice_error: str = "语音未启用"
        self._stt = None  # WhisperSTT 实例缓存（避免每次录音重载模型）
        # devices
        self.mihome = None
        self.mihome_error: str = "米家未启用"
        self.bluetooth = None
        self.bluetooth_error: str = "蓝牙未启用"
        self.intent_router = None
        # cluster
        self.registry = None
        self.cluster_error: str = "集群未启用"

    # ------------------------------------------------------------------ 装配
    def assemble(self) -> None:
        """按 settings 全量（重）装配。可重复调用（设置变更后刷新）。"""
        self._assemble_devices()  # 先于引擎：引擎可选注入 intent_router
        self._assemble_core()
        self._assemble_voice()
        self._assemble_cluster()

    def refresh_optional(self) -> None:
        """设置变更后刷新可选子系统；core import 失败不清空已有引擎。"""
        try:
            self.assemble()
        except ImportError as exc:  # core 必装，但刷新时不打断已运行的控制台
            _log().warning("刷新子系统失败（core 不可导入）：%s", exc)

    def _data_path(self, name: str) -> str:
        try:
            base = Path(self.settings.data_dir)
            base.mkdir(parents=True, exist_ok=True)
            return str(base / name)
        except Exception:
            return name  # 目录不可建时退回 cwd，由 core 自行处理

    def _assemble_core(self) -> None:
        # core 必装：ImportError 直接向上传播
        from core.emotion import EmotionTracker
        from core.engine import CompanionEngine
        from core.llm import create_backend
        from core.memory import MemoryStore
        from core.persona import PersonaManager

        log = _log()
        try:
            self.persona_manager = PersonaManager()
            self.persona_error = ""
        except Exception as exc:
            self.persona_manager = None
            self.persona_error = str(exc)
            log.warning("人格系统装配失败：%s", exc)

        try:
            self.emotion = EmotionTracker(self._data_path("emotion.json"))
            self.emotion_error = ""
        except Exception as exc:
            self.emotion = None
            self.emotion_error = str(exc)
            log.warning("情绪模块装配失败：%s", exc)

        try:
            if self.persona_manager is None:
                raise RuntimeError(f"人格系统不可用：{self.persona_error}")
            if self.emotion is None:
                raise RuntimeError(f"情绪模块不可用：{self.emotion_error}")
            memory = MemoryStore(self._data_path("memory.db"))
            backend = create_backend(self.settings)
            self.engine = CompanionEngine(
                self.settings,
                backend,
                self.persona_manager,
                memory,
                self.emotion,
                intent_router=self.intent_router,
            )
            self.engine_error = ""
        except Exception as exc:
            self.engine = None
            self.engine_error = str(exc)
            log.warning("对话引擎装配失败（聊天端点将降级）：%s", exc)

    def _assemble_voice(self) -> None:
        if not getattr(self.settings, "voice_enabled", False):
            self.voice = None
            self.voice_error = "语音未启用（settings.voice_enabled=false）"
            return
        if self.engine is None:
            self.voice = None
            self.voice_error = f"对话引擎不可用：{self.engine_error}"
            return
        try:
            from voice.pipeline import VoicePipeline  # 懒加载

            self.voice = VoicePipeline(self.settings, self.engine)
            self.voice_error = ""
        except Exception as exc:
            self.voice = None
            self.voice_error = str(exc)
            _log().warning("语音管线装配失败（语音端点降级）：%s", exc)

    def _assemble_devices(self) -> None:
        log = _log()
        self.mihome = None
        self.mihome_error = "米家未启用（settings.mihome_enabled=false）"
        if getattr(self.settings, "mihome_enabled", False):
            try:
                from devices.mihome import MiHome  # 懒加载

                self.mihome = MiHome(mode=getattr(self.settings, "mihome_mode", "lan"))
                self.mihome_error = ""
            except Exception as exc:
                self.mihome_error = str(exc)
                log.warning("米家装配失败（设备端点降级）：%s", exc)

        self.bluetooth = None
        self.bluetooth_error = "蓝牙未启用（settings.bluetooth_enabled=false）"
        if getattr(self.settings, "bluetooth_enabled", False):
            try:
                from devices.bluetooth_manager import BluetoothManager  # 懒加载

                self.bluetooth = BluetoothManager()
                self.bluetooth_error = ""
            except Exception as exc:
                self.bluetooth_error = str(exc)
                log.warning("蓝牙装配失败（设备端点降级）：%s", exc)

        self.intent_router = None
        if self.mihome is not None:
            try:
                from devices.intent import IntentRouter  # 懒加载

                self.intent_router = IntentRouter(self.mihome)
            except Exception as exc:
                log.warning("意图路由装配失败（聊天不联动设备）：%s", exc)

    def _assemble_cluster(self) -> None:
        if not getattr(self.settings, "cluster_enabled", False):
            self.registry = None
            self.cluster_error = "集群未启用（settings.cluster_enabled=false）"
            return
        try:
            from cluster.registry import NodeRegistry  # 懒加载

            self.registry = NodeRegistry()
            self.cluster_error = ""
        except Exception as exc:
            self.registry = None
            self.cluster_error = str(exc)
            _log().warning("集群装配失败（集群端点降级）：%s", exc)

    # ------------------------------------------------------------------ 设置
    def persist_settings(self) -> None:
        """尽力持久化 settings；文件不可写时只记日志不抛错。"""
        try:
            from core.config import save_settings

            save_settings(self.settings)
        except Exception as exc:
            _log().warning("settings 持久化失败（仅在内存中生效）：%s", exc)

    def update_settings(self, updates: dict) -> tuple[set, set]:
        """按当前字段类型做轻量 coercion 后更新；返回 (applied, ignored)。"""
        from dataclasses import fields, is_dataclass

        if is_dataclass(self.settings):
            known = {f.name for f in fields(self.settings)}
        else:  # pragma: no cover - 防御非 dataclass 实现
            known = set(vars(self.settings))
        applied: set = set()
        ignored: set = set()
        for key, value in (updates or {}).items():
            if key not in known:
                ignored.add(key)
                continue
            current = getattr(self.settings, key)
            setattr(self.settings, key, _coerce(value, current))
            applied.add(key)
        if applied:
            self.persist_settings()
        return applied, ignored


def _coerce(value, current):
    """按现有值类型做宽松类型转换（bool 注意先于 int 判断）。"""
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on", "是"}
    if isinstance(current, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return current
    if isinstance(current, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return current
    if current is None:
        return value
    return value if isinstance(value, type(current)) else str(value)


def create_app(settings) -> FastAPI:
    """装配 FastAPI 应用（SPEC §3.10）。core 不可导入时抛 ImportError。"""
    state = HermesState(settings)
    state.assemble()

    app = FastAPI(
        title=f"{getattr(settings, 'app_name', '栖伴')} 控制台",
        version="0.1.0",
    )
    app.state.hermes = state
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from ui.routes import router as rest_router
    from ui.ws import router as ws_router

    app.include_router(rest_router)
    app.include_router(ws_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():  # 单页控制台入口
        return FileResponse(STATIC_DIR / "index.html")

    _log().info(
        "%s 控制台就绪：engine=%s voice=%s mihome=%s bluetooth=%s cluster=%s",
        getattr(settings, "app_name", "栖伴"),
        "ok" if state.engine else f"降级({state.engine_error})",
        "ok" if state.voice else "off",
        "ok" if state.mihome else "off",
        "ok" if state.bluetooth else "off",
        "ok" if state.registry else "off",
    )
    return app
