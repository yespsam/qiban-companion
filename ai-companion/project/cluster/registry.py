"""栖伴集群：JSON 文件节点注册表（SPEC §3.9）。

- 原子写入：先写同目录临时文件，再 ``os.replace`` 覆盖，杜绝半截 JSON。
- ``alive()`` 按心跳 ttl 过滤掉超时节点。
- 进程内用锁保证并发安全；跨进程以文件内容为最终事实（后写覆盖）。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path

from core.logging_utils import get_logger

from .node import NodeInfo

logger = get_logger(__name__)


class NodeRegistry:
    """节点注册表：register / heartbeat / alive / deregister。"""

    def __init__(self, path: str = "data/cluster_nodes.json"):
        self.path = Path(path)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ 公共接口

    def register(self, info: NodeInfo) -> None:
        """注册（或全量更新）一个节点；last_heartbeat 为 0 时自动置为当前时间。"""
        if not info.node_id:
            raise ValueError("NodeInfo.node_id 不能为空")
        if not info.last_heartbeat:
            info.last_heartbeat = time.time()
        with self._lock:
            nodes = self._load_unlocked()
            nodes[info.node_id] = info
            self._save_unlocked(nodes)
        logger.info("节点已注册: %s (%s:%s models=%s)", info.node_id, info.host, info.port, info.models)

    def heartbeat(self, node_id: str) -> None:
        """刷新节点心跳时间戳；未知节点仅告警、不报错。"""
        with self._lock:
            nodes = self._load_unlocked()
            node = nodes.get(node_id)
            if node is None:
                logger.warning("收到未知节点的心跳: %s（忽略）", node_id)
                return
            node.last_heartbeat = time.time()
            self._save_unlocked(nodes)

    def alive(self, ttl: float = 30.0) -> list[NodeInfo]:
        """返回 ttl 秒内有心跳的节点，按 node_id 排序保证确定性。"""
        now = time.time()
        with self._lock:
            nodes = self._load_unlocked()
        return sorted(
            (n for n in nodes.values() if now - n.last_heartbeat <= ttl),
            key=lambda n: n.node_id,
        )

    def deregister(self, node_id: str) -> None:
        """摘除节点；不存在时静默忽略。"""
        with self._lock:
            nodes = self._load_unlocked()
            if node_id in nodes:
                del nodes[node_id]
                self._save_unlocked(nodes)
                logger.info("节点已摘除: %s", node_id)

    def all_nodes(self) -> list[NodeInfo]:
        """返回全部已注册节点（含超时节点，供 UI 展示用），按 node_id 排序。"""
        with self._lock:
            nodes = self._load_unlocked()
        return sorted(nodes.values(), key=lambda n: n.node_id)

    # ------------------------------------------------------------------ 内部实现

    def _load_unlocked(self) -> dict[str, NodeInfo]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("注册表读取失败，按空表处理: %s (%s)", self.path, exc)
            return {}
        if not isinstance(raw, dict):
            logger.warning("注册表格式异常（顶层非 dict），按空表处理: %s", self.path)
            return {}
        nodes: dict[str, NodeInfo] = {}
        for node_id, data in raw.items():
            try:
                nodes[node_id] = NodeInfo.from_dict(data)
            except (TypeError, ValueError) as exc:
                logger.warning("跳过损坏的节点记录 %s: %s", node_id, exc)
        return nodes

    def _save_unlocked(self, nodes: dict[str, NodeInfo]) -> None:
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {nid: n.to_dict() for nid, n in nodes.items()},
            ensure_ascii=False, indent=2, sort_keys=True,
        )
        fd, tmp_path = tempfile.mkstemp(
            dir=str(parent), prefix=self.path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)  # 原子替换
        except OSError:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
