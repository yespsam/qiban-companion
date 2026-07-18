"""WebSocket 流式聊天（SPEC §3.10 / §3.3）。

协议：
- 客户端发送 ``{"text": "..."}``。
- 服务端按 ``engine.chat_stream`` 逐段推送
  ``{"type": "thinking"|"text", "delta": "..."}``，
  结束推送 ``{"type": "done", "result": ChatResult(JSON)}``。
- 引擎不可用 / 消息非法 / 流式中途异常时推送
  ``{"type": "error", "message": "..."}`` 错误帧（连接保持）。
"""
from __future__ import annotations

import asyncio
import threading

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder

router = APIRouter()

_DONE = object()  # 流结束哨兵


@router.websocket("/ws/chat")
async def chat_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    state = websocket.app.state.hermes

    while True:
        try:
            payload = await websocket.receive_json()
        except WebSocketDisconnect:
            return
        except Exception:
            # 非 JSON / 结构非法：回错误帧，不断线
            if not await _send(websocket, {"type": "error", "message": "消息格式错误：请发送 JSON {\"text\": \"...\"}"}):
                return
            continue

        text = str((payload or {}).get("text") or "").strip()
        if not text:
            if not await _send(websocket, {"type": "error", "message": "消息不能为空"}):
                return
            continue

        engine = getattr(state, "engine", None)
        if engine is None:
            detail = getattr(state, "engine_error", "") or "未知原因"
            if not await _send(websocket, {"type": "error", "message": f"对话引擎不可用：{detail}"}):
                return
            continue

        if not await _pump_stream(websocket, engine, text):
            return


async def _pump_stream(websocket: WebSocket, engine, text: str) -> bool:
    """把同步生成器 engine.chat_stream 桥接到异步 WS；返回 False 表示连接已断。"""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def worker() -> None:
        try:
            for event in engine.chat_stream(text):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as exc:  # 流式中途异常 → 错误帧
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "error", "message": f"对话流中断：{exc}"}
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    threading.Thread(target=worker, daemon=True).start()

    while True:
        event = await queue.get()
        if event is _DONE:
            return True
        if isinstance(event, dict) and event.get("type") == "done":
            # ChatResult 为 dataclass，统一转 JSON 友好结构
            event = {"type": "done", "result": jsonable_encoder(event.get("result"))}
        if not await _send(websocket, event):
            return False


async def _send(websocket: WebSocket, frame: dict) -> bool:
    try:
        await websocket.send_json(frame)
        return True
    except Exception:
        return False
