"""米家智能家居（SPEC §3.8）。

- LAN 模式：python-miio 局域网发现与控制（miio 仅在实际调用时 import——懒加载铁律）。
- cloud 模式：micloud 拉取设备列表（含 token），同样懒加载；账号可用参数或
  环境变量 MIHOME_USER / MIHOME_PASSWORD 提供。
- 设备缓存：data/mihome_devices.json（相对路径基于项目根，HERMES_HOME 可覆盖）。
- control() 统一返回 {"ok": bool, ...}，任何异常都不外抛。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from core.logging_utils import get_logger
except Exception:  # pragma: no cover - 兜底
    import logging

    def get_logger(name: str) -> "logging.Logger":
        return logging.getLogger(name)


log = get_logger("devices.mihome")


@dataclass
class MiDevice:
    did: str
    name: str
    model: str
    ip: str = ""
    token: str = ""
    online: bool = True


def _resolve_path(p: str) -> Path:
    """相对路径基于项目根解析（HERMES_HOME 可覆盖项目根）。"""
    path = Path(p)
    if path.is_absolute():
        return path
    base = os.environ.get("HERMES_HOME")
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / path


class MiHome:
    """米家设备发现 / 控制门面。所有方法在依赖缺失或硬件不可用时安全降级。"""

    def __init__(
        self,
        mode: str = "lan",
        cfg_path: str = "data/mihome_devices.json",
        cloud_user: str | None = None,
        cloud_password: str | None = None,
        discover_timeout: float = 5.0,
    ):
        if mode not in ("lan", "cloud"):
            log.warning("未知米家模式 %r，按 lan 处理", mode)
            mode = "lan"
        self.mode = mode
        self.cfg_path = _resolve_path(cfg_path)
        self.cloud_user = cloud_user or os.environ.get("MIHOME_USER", "")
        self.cloud_password = cloud_password or os.environ.get("MIHOME_PASSWORD", "")
        self.discover_timeout = discover_timeout

    # ---------------- 发现 ----------------

    def discover(self) -> list[MiDevice]:
        """LAN: miio mDNS 发现；cloud: micloud 拉取云端设备列表。
        依赖缺失 / 网络失败时记日志并返回 []（不抛异常）。"""
        if self.mode == "cloud":
            return self._discover_cloud()
        return self._discover_lan()

    def _discover_lan(self) -> list[MiDevice]:
        try:
            import miio  # noqa: F401  懒加载
        except Exception as exc:
            log.warning("python-miio 不可用（%s），LAN 设备发现跳过", exc)
            return []
        try:
            from miio import Discovery

            found = Discovery.discover_mdns(timeout=self.discover_timeout)
        except Exception as exc:
            log.error("米家 LAN 发现失败：%s", exc)
            return []

        old = {d.did: d for d in self._load_cache()}
        devices: list[MiDevice] = []
        items = found.items() if isinstance(found, dict) else enumerate(found or [])
        for ip, dev in items:
            ip = str(ip)
            did = str(getattr(dev, "device_id", "") or getattr(dev, "did", "") or ip)
            model = str(getattr(dev, "model", "") or "")
            prev = old.get(did)
            devices.append(
                MiDevice(
                    did=did,
                    name=(prev.name if prev else "") or model or f"miio-{did}",
                    model=model or (prev.model if prev else ""),
                    ip=ip,
                    token=(prev.token if prev else ""),  # LAN 发现拿不到 token，沿用缓存
                    online=True,
                )
            )
        self._save_cache(devices)
        log.info("米家 LAN 发现 %d 台设备", len(devices))
        return devices

    def _discover_cloud(self) -> list[MiDevice]:
        if not (self.cloud_user and self.cloud_password):
            log.warning("cloud 模式需要米家账号（参数或环境变量 MIHOME_USER/MIHOME_PASSWORD）")
            return []
        try:  # micloud 包结构为 micloud.micloud.MiCloud，做两层尝试
            try:
                from micloud.micloud import MiCloud  # 懒加载
            except ImportError:
                from micloud import MiCloud  # type: ignore  懒加载
        except Exception as exc:
            log.warning("micloud 不可用（%s），云端设备发现跳过", exc)
            return []
        try:
            mc = MiCloud(self.cloud_user, self.cloud_password)
            mc.login()
            raw = mc.get_devices() or []
        except Exception as exc:
            log.error("micloud 拉取设备列表失败：%s", exc)
            return []

        old = {d.did: d for d in self._load_cache()}
        devices: list[MiDevice] = []
        for d in raw:
            if not isinstance(d, dict):
                continue
            did = str(d.get("did") or d.get("deviceID") or "")
            if not did:
                continue
            prev = old.get(did)
            devices.append(
                MiDevice(
                    did=did,
                    name=str(d.get("name") or (prev.name if prev else "") or did),
                    model=str(d.get("model") or ""),
                    ip=str(d.get("localip") or d.get("ip") or (prev.ip if prev else "")),
                    token=str(d.get("token") or (prev.token if prev else "")),
                    online=bool(d.get("isOnline", True)),
                )
            )
        self._save_cache(devices)
        log.info("米家云端拉取到 %d 台设备", len(devices))
        return devices

    # ---------------- 控制 / 状态 ----------------

    def control(self, did: str, action: str, params: list | None = None) -> dict:
        """统一控制入口：经 miio.Device.send 下发。永不抛异常，
        返回 {"ok": bool, "did":..., "action":..., ...}。"""
        params = list(params or [])
        base = {"did": did, "action": action, "params": params}

        dev = self.get_device(did)
        if dev is None:
            log.warning("控制失败：未知设备 %s", did)
            return {"ok": False, "error": f"未知设备: {did}", **base}
        if not dev.ip:
            log.warning("控制失败：设备 %s 无局域网 IP", did)
            return {"ok": False, "error": "设备无局域网 IP，无法控制", **base}
        try:
            import miio  # 懒加载
        except Exception as exc:
            log.error("python-miio 不可用（%s），无法控制 %s", exc, did)
            return {"ok": False, "error": f"python-miio 不可用: {exc}", **base}
        try:
            device = miio.Device(dev.ip, dev.token or "")
            result = device.send(action, params)
            log.info("控制成功 %s.%s(%s) -> %s", did, action, params, result)
            return {"ok": True, "result": result, **base}
        except Exception as exc:
            log.error("控制 %s 执行 %s 失败：%s", did, action, exc)
            return {"ok": False, "error": str(exc), **base}

    def status(self, did: str) -> dict:
        """查询设备基础信息（miIO.info，对所有 miio 设备通用）。永不抛异常。"""
        dev = self.get_device(did)
        if dev is None:
            return {"ok": False, "error": f"未知设备: {did}", "did": did}
        if not dev.ip:
            return {"ok": False, "error": "设备无局域网 IP", "did": did}
        try:
            import miio  # 懒加载
        except Exception as exc:
            log.error("python-miio 不可用（%s），无法查询 %s", exc, did)
            return {"ok": False, "error": f"python-miio 不可用: {exc}", "did": did}
        try:
            info = miio.Device(dev.ip, dev.token or "").info()
            data = {}
            for attr in ("model", "fw_ver", "fw_version", "hw_ver", "hw_version", "mac"):
                value = getattr(info, attr, None)
                if value:
                    data[attr] = value
            return {"ok": True, "did": did, "info": data}
        except Exception as exc:
            log.error("查询 %s 状态失败：%s", did, exc)
            return {"ok": False, "error": str(exc), "did": did}

    # ---------------- 缓存 / 解析 ----------------

    def list_devices(self) -> list[MiDevice]:
        """读取缓存的设备列表。"""
        return self._load_cache()

    def get_device(self, did: str) -> MiDevice | None:
        for d in self._load_cache():
            if d.did == did:
                return d
        return None

    def resolve(self, name_or_did: str) -> str:
        """把设备名/别名解析成 did；解析不到则原样返回（由 control 报未知设备）。"""
        for d in self._load_cache():
            if d.did == name_or_did or d.name == name_or_did:
                return d.did
        return name_or_did

    def add_device(
        self, did: str, name: str = "", model: str = "", ip: str = "", token: str = ""
    ) -> MiDevice:
        """手动登记/更新一台设备（LAN 模式下固件较新的设备拿不到 token，需手动填）。"""
        devices = {d.did: d for d in self._load_cache()}
        prev = devices.get(did)
        dev = MiDevice(
            did=did,
            name=name or (prev.name if prev else "") or did,
            model=model or (prev.model if prev else ""),
            ip=ip or (prev.ip if prev else ""),
            token=token or (prev.token if prev else ""),
            online=True,
        )
        devices[did] = dev
        self._save_cache(list(devices.values()))
        log.info("已登记米家设备 %s (%s)", did, dev.name)
        return dev

    def _load_cache(self) -> list[MiDevice]:
        try:
            raw = json.loads(self.cfg_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except Exception as exc:
            log.error("读取设备缓存 %s 失败：%s", self.cfg_path, exc)
            return []
        items = raw.get("devices", raw) if isinstance(raw, dict) else raw
        out: list[MiDevice] = []
        for it in items or []:
            try:
                out.append(
                    MiDevice(
                        did=str(it.get("did", "")),
                        name=str(it.get("name", "")),
                        model=str(it.get("model", "")),
                        ip=str(it.get("ip", "")),
                        token=str(it.get("token", "")),
                        online=bool(it.get("online", True)),
                    )
                )
            except Exception as exc:
                log.warning("跳过损坏的米家设备记录：%s (%s)", it, exc)
        return [d for d in out if d.did]

    def _save_cache(self, devices: list[MiDevice]) -> None:
        payload = {"devices": [asdict(d) for d in devices]}
        try:
            self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
            self.cfg_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            log.error("写入设备缓存 %s 失败：%s", self.cfg_path, exc)
