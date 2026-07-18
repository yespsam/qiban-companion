"""栖伴集群：节点路由（SPEC §3.9）。

- ``pick`` 支持两种策略：``least_load``（负载最小）/ ``local_first``（本机优先）。
- ``route_chat`` 对选中节点发起 OpenAI 兼容的 ``/v1/chat/completions`` HTTP 调用
  （httpx 同步）；无可用节点或调用失败时抛出 :class:`ClusterUnavailable`。
- ``GenerateResult`` 懒导入自 ``core.llm.base``（feat/core 合并前用同字段的本地
  兜底 dataclass，保证 cluster 模块可独立导入与测试）。
"""
from __future__ import annotations

import socket
from dataclasses import dataclass

import httpx

from core.logging_utils import get_logger

from .node import NodeInfo
from .registry import NodeRegistry

logger = get_logger(__name__)


class ClusterUnavailable(Exception):
    """集群中没有可用节点，或选中节点调用失败。"""


@dataclass
class _LocalGenerateResult:
    """core.llm.base.GenerateResult 的就地兜底（字段与 SPEC §3.4 完全一致）。"""

    text: str
    reasoning: str
    model: str
    tokens: int


def _generate_result_class():
    """优先返回 core.llm.base.GenerateResult；合并前退回本地同字段实现。"""
    try:
        from core.llm.base import GenerateResult  # 懒加载：core 分支可能尚未合并

        return GenerateResult
    except Exception:  # noqa: BLE001 —— 模块不存在/导入失败均走兜底
        return _LocalGenerateResult


def _detect_local_ids() -> set[str]:
    """尽力收集「本机」标识集合，用于 local_first 策略；失败时只含回环地址。"""
    ids = {"127.0.0.1", "localhost", "::1"}
    try:
        hostname = socket.gethostname()
        if hostname:
            ids.add(hostname)
        try:
            ip = socket.gethostbyname(hostname)
            if ip:
                ids.add(ip)
        except OSError:
            pass
        try:
            ids.update(socket.gethostbyname_ex(hostname)[2])
        except OSError:
            pass
    except OSError:
        pass
    return ids


class ClusterRouter:
    """按注册表把对话请求路由到最合适的存活节点。"""

    def __init__(
        self,
        registry: NodeRegistry,
        ttl: float = 30.0,
        timeout: float = 60.0,
        local_ids: set[str] | None = None,
    ):
        """
        :param registry: 节点注册表。
        :param ttl: 心跳存活窗口（秒），与 NodeRegistry.alive 的 ttl 对齐。
        :param timeout: 调用节点 HTTP 接口的超时时间（秒）。
        :param local_ids: 视为「本机」的 host/node_id 集合；默认自动探测。
        """
        self.registry = registry
        self.ttl = ttl
        self.timeout = timeout
        self._local_ids = set(local_ids) if local_ids is not None else _detect_local_ids()

    # ------------------------------------------------------------------ 选点

    def pick(self, model_id: str, prefer: str = "least_load") -> NodeInfo | None:
        """从「存活且持有所需模型」的节点中选一个；没有候选返回 None。

        - ``least_load``：选 load 最小者（并列时按 node_id 字典序，保证确定性）。
        - ``local_first``：候选中有本机节点时在本机节点中选 load 最小者，
          否则退化为 least_load。
        """
        candidates = [n for n in self.registry.alive(self.ttl) if model_id in n.models]
        if not candidates:
            return None
        if prefer == "least_load":
            return min(candidates, key=lambda n: (n.load, n.node_id))
        if prefer == "local_first":
            local = [n for n in candidates if self._is_local(n)]
            pool = local if local else candidates
            return min(pool, key=lambda n: (n.load, n.node_id))
        raise ValueError(f"未知选点策略: {prefer!r}（支持 least_load / local_first）")

    # ------------------------------------------------------------------ 路由

    def route_chat(
        self,
        messages: list[dict],
        model_id: str,
        prefer: str = "least_load",
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ):
        """选中节点并调用其 OpenAI 兼容接口，返回 GenerateResult。

        无可用节点 / HTTP 错误 / 响应无法解析 → 抛 ClusterUnavailable。
        """
        node = self.pick(model_id, prefer=prefer)
        if node is None:
            raise ClusterUnavailable(
                f"没有可路由的存活节点持有模型 {model_id!r}（ttl={self.ttl}s）"
            )
        url = f"{node.endpoint()}/v1/chat/completions"
        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        logger.info("路由到节点 %s (%s) model=%s", node.node_id, url, model_id)
        try:
            resp = httpx.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001 —— httpx/JSON 错误统一转换
            raise ClusterUnavailable(f"节点 {node.node_id}({url}) 调用失败: {exc}") from exc
        return self._parse_response(data, model_id, node)

    # ------------------------------------------------------------------ 内部

    def _is_local(self, node: NodeInfo) -> bool:
        return node.host in self._local_ids or node.node_id in self._local_ids

    @staticmethod
    def _parse_response(data: dict, model_id: str, node: NodeInfo):
        """解析 OpenAI chat.completion 响应为 GenerateResult。"""
        try:
            choice = data["choices"][0]
            message = choice.get("message") or {}
            text = message.get("content") or ""
            # llama.cpp / Ollama 的推理模型经 OpenAI 兼容层输出 reasoning_content
            reasoning = message.get("reasoning_content") or ""
            usage = data.get("usage") or {}
            tokens = int(usage.get("total_tokens") or 0)
        except (KeyError, IndexError, AttributeError, TypeError, ValueError) as exc:
            raise ClusterUnavailable(
                f"节点 {node.node_id} 返回了无法解析的响应: {exc}"
            ) from exc
        result_cls = _generate_result_class()
        return result_cls(
            text=text,
            reasoning=reasoning,
            model=str(data.get("model") or model_id),
            tokens=tokens,
        )
