"""REST API（SPEC §3.10 全部端点 + 便捷聚合 /api/state）。

约定：
- 可选子系统（voice/devices/cluster）未启用或装配失败时，
  对应端点返回 ``{"enabled": false, "error": ...}``（HTTP 200）。
- core 运行时故障（engine/persona 不可用）返回 503。
- 所有 dataclass 响应统一经 ``jsonable_encoder`` 转 JSON。
"""
from __future__ import annotations

import importlib
import inspect
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from core.logging_utils import get_logger
from voice.casting import (is_clone_engine_name, list_voice_resources,
                           prosody_kwargs, resolve_cast, resolve_clone_ref)

logger = get_logger(__name__)

router = APIRouter()

_AUDIO_MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".webm": "audio/webm",
}
_AUDIO_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
}


def _state(request: Request):
    return request.app.state.hermes


def _unavailable(name: str, error: str = "") -> dict:
    return {"enabled": False, "error": error or f"{name}未启用或不可用"}


def _err(status: int, message: str, **extra) -> JSONResponse:
    return JSONResponse({"error": message, **extra}, status_code=status)


async def _maybe_await(result):
    """兼容 SPEC 声明的 async 方法与潜在的同步实现。"""
    if inspect.isawaitable(result):
        return await result
    return result


# ---------------------------------------------------------------------- 人格
@router.get("/api/personas")
def list_personas(request: Request):
    """GET /api/personas → [{id, display_name, gender, active}]"""
    st = _state(request)
    if st.persona_manager is None:
        return _err(503, "人格系统不可用", detail=st.persona_error)
    active = getattr(st.settings, "active_persona", "")
    return [
        {
            "id": p.id,
            "display_name": p.display_name,
            "gender": p.gender,
            "traits": list(getattr(p, "traits", []) or []),
            "active": p.id == active,
        }
        for p in st.persona_manager.list_personas()
    ]


@router.post("/api/persona/select")
def select_persona(request: Request, payload: dict = Body(...)):
    """POST /api/persona/select → {persona_id}"""
    st = _state(request)
    if st.persona_manager is None:
        return _err(503, "人格系统不可用", detail=st.persona_error)
    persona_id = str(payload.get("persona_id") or "").strip()
    if not persona_id:
        return _err(400, "缺少 persona_id")
    try:
        persona = st.persona_manager.get(persona_id)
    except KeyError:
        return _err(404, f"人格不存在：{persona_id}")
    st.settings.active_persona = persona_id
    st.persist_settings()
    return {
        "ok": True,
        "active_persona": persona_id,
        "display_name": persona.display_name,
        "gender": persona.gender,
    }


# ------------------------------------------------------------------ 关系身份
@router.get("/api/relationships")
def list_relationships(request: Request):
    """GET /api/relationships → [{id, display_name, active}]（SPEC §3.2a）"""
    st = _state(request)
    if st.persona_manager is None:
        return _err(503, "人格系统不可用", detail=st.persona_error)
    active = getattr(st.settings, "active_relationship", "lover")
    return [
        {
            "id": r["id"],
            "display_name": r["display_name"],
            "active": r["id"] == active,
        }
        for r in st.persona_manager.list_relationships()
    ]


@router.post("/api/relationship/select")
def select_relationship(request: Request, payload: dict = Body(...)):
    """POST /api/relationship/select → {relationship_id}

    写入 settings 并持久化；引擎每轮实时读取 settings.active_relationship，
    无需重建引擎即可热更新。
    """
    st = _state(request)
    if st.persona_manager is None:
        return _err(503, "人格系统不可用", detail=st.persona_error)
    rel_id = str(payload.get("relationship_id") or "").strip()
    if not rel_id:
        return _err(400, "缺少 relationship_id")
    try:
        rel = st.persona_manager.get_relationship(rel_id)
    except KeyError:
        return _err(404, f"关系身份不存在：{rel_id}")
    st.settings.active_relationship = rel_id
    st.persist_settings()
    return {
        "ok": True,
        "active_relationship": rel_id,
        "display_name": rel["display_name"],
    }


# ---------------------------------------------------------------------- 聊天
@router.post("/api/chat")
async def chat(request: Request, payload: dict = Body(...)):
    """POST /api/chat → {text} → ChatResult(JSON)"""
    st = _state(request)
    if st.engine is None:
        return _err(503, "对话引擎不可用", detail=st.engine_error)
    text = str(payload.get("text") or "").strip()
    if not text:
        return _err(400, "消息不能为空")
    try:
        result = await run_in_threadpool(st.engine.chat, text)
    except Exception as exc:
        return _err(500, f"对话失败：{exc}")
    return jsonable_encoder(result)


# ---------------------------------------------------------------------- 语音
@router.post("/api/voice/speak")
async def voice_speak(request: Request):
    """POST /api/voice/speak

    - ``application/json``  body ``{"text": ...}``：触发 TTS。
      能合成到文件则直接返回音频流（audio/*），否则经 VoicePipeline
      服务端本地播放并返回 ``{"ok": true, "mode": "server_playback"}``。
    - 其余 content-type（浏览器 MediaRecorder 录音，audio/*）：转写为文本，
      返回 ``{"ok": true, "text": ...}``。
    - 语音未启用：``{"enabled": false, "error": ...}``。
    """
    st = _state(request)
    if not getattr(st.settings, "voice_enabled", False):
        return _unavailable("语音", st.voice_error)

    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype == "application/json":
        payload = await request.json()
        text = str((payload or {}).get("text") or "").strip()
        if not text:
            return _err(400, "缺少 text")
        mood = str((payload or {}).get("mood") or "").strip() or None
        archetype = str((payload or {}).get("archetype") or "").strip() or None
        persona_id = _normalize_persona_id((payload or {}).get("persona"))
        relationship_id = str((payload or {}).get("relationship") or "").strip() or None
        return await _tts_reply(st, text, mood, archetype, persona_id, relationship_id)

    audio = await request.body()
    if not audio:
        return _err(400, "空音频：请使用麦克风录制后再发送")
    return await _stt_transcribe(st, audio, ctype)


@router.post("/api/voice/transcribe")
async def voice_transcribe(request: Request):
    """POST /api/voice/transcribe → 浏览器录音转文字。"""
    st = _state(request)
    if not getattr(st.settings, "voice_enabled", False):
        return _unavailable("语音", st.voice_error)
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    audio = await request.body()
    if not audio:
        return _err(400, "空音频：请使用麦克风录制后再发送")
    return await _stt_transcribe(st, audio, ctype)


@router.get("/api/voice/voices")
def voice_voices(request: Request, persona: Optional[str] = None):
    """GET /api/voice/voices → 当前人格可选声线资源。"""
    st = _state(request)
    persona_id = _normalize_persona_id(persona) or getattr(st.settings, "active_persona", "")
    persona_obj = None
    if st.persona_manager is not None:
        try:
            persona_obj = st.persona_manager.get(persona_id)
        except Exception:
            persona_obj = None
    gender = getattr(persona_obj, "gender", None)
    voice_cfg = getattr(persona_obj, "voice", None) or {}
    resources = list_voice_resources(
        persona_id,
        getattr(st.settings, "active_relationship", None),
        persona_voice=voice_cfg if isinstance(voice_cfg, dict) else None,
        gender=gender,
    )
    active = getattr(st.settings, "active_archetype", "") or ""
    if active and active not in {item["archetype"] for item in resources}:
        active = ""
    return {
        "enabled": bool(getattr(st.settings, "voice_enabled", False)),
        "pipeline_ready": st.voice is not None,
        "tts_engine": getattr(st.settings, "tts_engine", ""),
        "persona": {
            "id": persona_id,
            "gender": gender,
            "display_name": getattr(persona_obj, "display_name", persona_id),
        },
        "active_archetype": active,
        "resources": resources,
        "providers": [
            {
                "id": "edge_tts",
                "name": "Edge Neural TTS",
                "status": "ready",
                "note": "当前默认真实声音资源，启动脚本会自动安装 edge-tts。",
            },
            {
                "id": "clone",
                "name": "本地克隆声优",
                "status": "reserved",
                "note": "接入 GPT-SoVITS / CosyVoice 兼容服务后可上传参考音频。",
            },
        ],
    }


@router.post("/api/voice/select")
def voice_select(request: Request, payload: dict = Body(...)):
    """POST /api/voice/select → 持久化当前声线 archetype。"""
    st = _state(request)
    persona_id = _normalize_persona_id((payload or {}).get("persona")) or getattr(
        st.settings, "active_persona", ""
    )
    persona_obj = None
    if st.persona_manager is not None:
        try:
            persona_obj = st.persona_manager.get(persona_id)
        except Exception:
            persona_obj = None
    raw = str((payload or {}).get("archetype") or (payload or {}).get("voice") or "").strip()
    archetype = "" if raw in {"", "default", "auto"} else raw
    resources = list_voice_resources(
        persona_id,
        getattr(st.settings, "active_relationship", None),
        persona_voice=getattr(persona_obj, "voice", None),
        gender=getattr(persona_obj, "gender", None),
    )
    allowed = {item["archetype"] for item in resources}
    if archetype not in allowed:
        return _err(400, f"声线不存在：{archetype}", allowed=sorted(item["id"] for item in resources))
    st.settings.active_archetype = archetype
    st.persist_settings()
    selected = next((item for item in resources if item["archetype"] == archetype), resources[0])
    return {
        "ok": True,
        "active_archetype": archetype,
        "selected": selected,
        "resources": resources,
    }


async def _tts_reply(
    st,
    text: str,
    mood: str | None = None,
    archetype: str | None = None,
    persona_id: str | None = None,
    relationship_id: str | None = None,
):
    persona = None
    if st.persona_manager is not None:
        try:
            persona = st.persona_manager.get(persona_id or st.settings.active_persona)
        except Exception:
            if persona_id:
                try:
                    persona = st.persona_manager.get(st.settings.active_persona)
                except Exception:
                    persona = None
            else:
                persona = None

    # 策略一：直接驱动 TTS 引擎合成到文件 → 音频流回给浏览器播放
    try:
        path = await run_in_threadpool(
            _synthesize_to_file, st, text, persona, mood, archetype, relationship_id
        )
        if path:
            suffix = Path(path).suffix.lower()
            return FileResponse(
                path,
                media_type=_AUDIO_MEDIA_TYPES.get(suffix, "application/octet-stream"),
                filename=Path(path).name,
            )
    except Exception as exc:
        st.voice_error = st.voice_error or str(exc)

    # 策略二：VoicePipeline 服务端播放（本机同机部署时可用）
    if st.voice is not None and persona is not None:
        try:
            if mood:
                st.voice._last_mood = mood  # SPEC §3.7a 情绪韵律
            await run_in_threadpool(st.voice.speak, text, persona)
            return {"ok": True, "mode": "server_playback", "text": text}
        except Exception as exc:
            return {"ok": False, "error": f"TTS 播放失败：{exc}"}
    return _unavailable("语音", st.voice_error or "TTS 引擎不可用")


def _normalize_persona_id(value) -> str | None:
    """接受 mobile demo 的 female/male 简写，也接受后端 persona id。"""
    raw = str(value or "").strip()
    aliases = {
        "female": "female_companion",
        "girl": "female_companion",
        "female_companion": "female_companion",
        "male": "male_companion",
        "boy": "male_companion",
        "male_companion": "male_companion",
    }
    return aliases.get(raw)


def _synthesize_to_file(
    st,
    text: str,
    persona,
    mood: str | None = None,
    archetype: str | None = None,
    relationship_id: str | None = None,
) -> str | None:
    engine = _make_tts_engine(st.settings)
    if engine is None:
        return None
    voice_cfg = getattr(persona, "voice", None) or {}
    # 声优选角（SPEC §3.7a/§3.7b）：人格×关系身份×心情×声线 → 音色/风格/韵律
    persona_id = getattr(persona, "id", "") or ""
    cast = resolve_cast(
        persona_id,
        relationship_id or getattr(st.settings, "active_relationship", None),
        mood,
        persona_voice=voice_cfg if isinstance(voice_cfg, dict) else None,
        archetype=archetype or (getattr(st.settings, "active_archetype", "") or None),
        gender=getattr(persona, "gender", None),
    )
    if is_clone_engine_name(getattr(st.settings, "tts_engine", "")):
        ref = resolve_clone_ref(persona_id)  # 克隆引擎：voice 参数携带参考音频路径
        if ref:
            cast["voice"] = ref
    out_dir = Path(st.settings.data_dir) / "tts_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"reply_{int(time.time() * 1000)}{getattr(engine, 'output_ext', '.mp3')}"
    try:
        result = engine.synthesize(
            text, voice=cast["voice"], out_path=str(out_path), style=cast["style"],
            **prosody_kwargs(engine, cast),
        )
    except TypeError:  # 容忍位置参数实现
        result = engine.synthesize(text, cast["voice"], str(out_path), cast["style"])
    return result or str(out_path)


@router.post("/api/voice/upload")
async def voice_upload(request: Request):
    """POST /api/voice/upload?target=default|female_companion|male_companion

    上传声优参考音频（原始音频字节为请求体，Content-Type: audio/*，3~10 秒干净人声）。
    保存到 data/voices/；target=default 写入 settings.clone_ref_audio 并持久化，
    人格 target 写入 voices.yaml 的 clone.voices 段（SPEC §3.7a）。
    settings.yaml 设置 tts_engine: clone 后，TA 即用此声音说话。
    """
    st = _state(request)
    if not getattr(st.settings, "voice_enabled", False):
        return _unavailable("语音", st.voice_error)
    target = request.query_params.get("target", "default")
    if target not in ("default", "female_companion", "male_companion"):
        return _err(400, "target 仅支持 default | female_companion | male_companion")
    audio = await request.body()
    if not audio or len(audio) < 100:
        return _err(400, "空音频：请上传 3~10 秒干净人声（wav/mp3/m4a）")
    if len(audio) > 20 * 1024 * 1024:
        return _err(400, "音频过大（上限 20MB）")
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    ext = _AUDIO_EXTENSIONS.get(ctype, ".wav")
    out_dir = Path(st.settings.data_dir) / "voices"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{target}_ref{ext}"
    out_path.write_bytes(audio)
    logger.info("已接收声优参考音频：%s（%d 字节, target=%s）", out_path, len(audio), target)

    settings_saved = False
    if target == "default":
        st.settings.clone_ref_audio = str(out_path)
        try:
            from core.config import save_settings

            save_settings(st.settings)
            settings_saved = True
        except Exception as exc:  # 持久化失败不影响本次生效
            logger.warning("clone_ref_audio 写回 settings.yaml 失败：%s", exc)
    voices_yaml_updated = _register_clone_voice(target, str(out_path))
    return {
        "ok": True,
        "target": target,
        "path": str(out_path),
        "bytes": len(audio),
        "settings_saved": settings_saved,
        "voices_yaml_updated": voices_yaml_updated,
        "hint": "settings.yaml 设置 tts_engine: clone 并启动 GPT-SoVITS 兼容服务后，TA 将用此声音说话",
    }


def _register_clone_voice(target: str, ref_path: str) -> bool:
    """把人格级参考音频写入 voices.yaml 的 clone.voices 段（尽力而为）。"""
    if target == "default":
        return False
    try:
        import yaml

        from voice.casting import DEFAULT_VOICES_PATH, clear_cache

        path = Path(DEFAULT_VOICES_PATH)
        data = {}
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                data = {}
        voices = data.setdefault("clone", {}).setdefault("voices", {})
        voices.setdefault(target, {})["ref_audio"] = ref_path
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                        encoding="utf-8")
        clear_cache()
        return True
    except Exception as exc:
        logger.warning("voices.yaml clone 段更新失败（不影响上传文件本身）：%s", exc)
        return False


def _make_tts_engine(settings):
    """按 settings.tts_engine 反射查找 TTSEngine 实现类（契约优先，尽力而为）。"""
    if is_clone_engine_name(getattr(settings, "tts_engine", "")):
        try:
            from voice.tts import CloneTTSEngine  # 懒加载

            return CloneTTSEngine(
                api_base=getattr(settings, "clone_api_base", "") or "http://127.0.0.1:9880",
                ref_audio=getattr(settings, "clone_ref_audio", "") or "",
                ref_text=getattr(settings, "clone_ref_text", "") or "",
            )
        except Exception:
            return None
    module_name = {
        "edge_tts": "voice.tts.edge_tts_engine",
        "piper": "voice.tts.piper_engine",
    }.get(getattr(settings, "tts_engine", "edge_tts"), "voice.tts.edge_tts_engine")
    try:
        from voice.tts.base import TTSEngine  # 懒加载

        module = importlib.import_module(module_name)
    except Exception:
        return None
    for obj in vars(module).values():
        if isinstance(obj, type) and issubclass(obj, TTSEngine) and obj is not TTSEngine:
            for args in ((), (settings,)):
                try:
                    return obj(*args)
                except TypeError:
                    continue
    return None


async def _stt_transcribe(st, audio: bytes, ctype: str):
    ext = _AUDIO_EXTENSIONS.get(ctype, ".webm")
    try:
        up_dir = Path(st.settings.data_dir) / "uploads"
        up_dir.mkdir(parents=True, exist_ok=True)
        fpath = up_dir / f"rec_{int(time.time() * 1000)}{ext}"
        fpath.write_bytes(audio)
        text = await run_in_threadpool(_transcribe_file, st, str(fpath))
        return {"ok": True, "text": text}
    except Exception as exc:
        return {"ok": False, "error": f"语音识别失败：{exc}"}


def _transcribe_file(st, path: str) -> str:
    from voice.stt import WhisperSTT  # 懒加载（faster-whisper 为重依赖）

    if st._stt is None:
        size = getattr(st.settings, "stt_model_size", "small")
        for args, kwargs in (
            ((), {"model_size": size}),
            ((size,), {}),
            ((), {}),
        ):
            try:
                st._stt = WhisperSTT(*args, **kwargs)
                break
            except TypeError:
                continue
        else:
            raise RuntimeError("WhisperSTT 初始化失败")
    return st._stt.transcribe(path)


@router.get("/api/voice/status")
def voice_status(request: Request):
    """GET /api/voice/status → 语音管线状态"""
    st = _state(request)
    enabled = bool(getattr(st.settings, "voice_enabled", False))
    cast = None
    if st.persona_manager is not None:
        try:
            persona = st.persona_manager.get(st.settings.active_persona)
            cast = resolve_cast(
                persona.id,
                getattr(st.settings, "active_relationship", None),
                None,
                persona_voice=getattr(persona, "voice", None),
                archetype=getattr(st.settings, "active_archetype", "") or None,
                gender=getattr(persona, "gender", None),
            )
        except Exception:
            cast = None
    return {
        "enabled": enabled and st.voice is not None,
        "voice_enabled": enabled,
        "pipeline_ready": st.voice is not None,
        "tts_engine": getattr(st.settings, "tts_engine", ""),
        "active_archetype": getattr(st.settings, "active_archetype", ""),
        "voice_profile": getattr(st.settings, "voice_profile", ""),
        "cast": cast,
        "stt_model_size": getattr(st.settings, "stt_model_size", ""),
        "error": "" if (enabled and st.voice is not None) else st.voice_error,
    }


# ---------------------------------------------------------------------- 设备
@router.get("/api/devices")
async def list_devices(request: Request):
    """GET /api/devices → 米家 + 蓝牙设备汇总"""
    st = _state(request)

    mihome = {"enabled": st.mihome is not None, "devices": [], "error": st.mihome_error}
    if st.mihome is not None:
        try:
            found = await run_in_threadpool(st.mihome.discover)
            mihome["devices"] = jsonable_encoder(found)
            mihome["error"] = ""
        except Exception as exc:
            mihome["error"] = str(exc)

    bluetooth = {
        "enabled": st.bluetooth is not None,
        "devices": [],
        "error": st.bluetooth_error,
    }
    if st.bluetooth is not None:
        try:
            bluetooth["devices"] = jsonable_encoder(st.bluetooth.list_saved())
            bluetooth["error"] = ""
        except Exception as exc:
            bluetooth["error"] = str(exc)

    return {"mihome": mihome, "bluetooth": bluetooth}


@router.post("/api/devices/control")
async def control_device(request: Request, payload: dict = Body(...)):
    """POST /api/devices/control → {did, action, params?, target?}

    target 缺省按 action 推断：scan/pair/connect → 蓝牙；其余 → 米家。
    """
    st = _state(request)
    action = str(payload.get("action") or "").strip()
    if not action:
        return _err(400, "缺少 action")
    target = payload.get("target") or (
        "bluetooth" if action in {"scan", "pair", "connect"} else "mihome"
    )

    if target == "bluetooth":
        if st.bluetooth is None:
            return _unavailable("蓝牙", st.bluetooth_error)
        try:
            if action == "scan":
                found = await _maybe_await(st.bluetooth.scan())
                return {"ok": True, "devices": jsonable_encoder(found)}
            if action in {"pair", "connect"}:
                address = str(payload.get("did") or payload.get("address") or "").strip()
                if not address:
                    return _err(400, "缺少设备地址 did")
                ok = await _maybe_await(getattr(st.bluetooth, action)(address))
                return {"ok": bool(ok), "address": address, "action": action}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return _err(400, f"蓝牙不支持的动作：{action}")

    if st.mihome is None:
        return _unavailable("米家", st.mihome_error)
    did = str(payload.get("did") or "").strip()
    if not did:
        return _err(400, "缺少 did")
    params = payload.get("params") or None
    try:
        result = await run_in_threadpool(st.mihome.control, did, action, params)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if isinstance(result, dict):
        return jsonable_encoder(result)
    return {"ok": True, "result": jsonable_encoder(result)}


# ---------------------------------------------------------------------- 设置
@router.get("/api/settings")
def get_settings(request: Request):
    """GET /api/settings → Settings(JSON)"""
    return jsonable_encoder(_state(request).settings)


@router.post("/api/settings")
async def update_settings(request: Request, payload: dict = Body(...)):
    """POST /api/settings → 部分更新并持久化，随后刷新可选子系统。"""
    st = _state(request)
    applied, ignored = st.update_settings(payload)
    if applied:
        await run_in_threadpool(st.refresh_optional)
    return {
        "ok": True,
        "applied": sorted(applied),
        "ignored": sorted(ignored),
        "settings": jsonable_encoder(st.settings),
    }


# ---------------------------------------------------------------------- 集群
@router.get("/api/cluster/nodes")
def cluster_nodes(request: Request):
    """GET /api/cluster/nodes → 集群节点列表"""
    st = _state(request)
    if st.registry is None:
        return {"enabled": False, "nodes": [], "error": st.cluster_error}
    try:
        nodes = st.registry.alive()
    except TypeError:
        nodes = st.registry.alive(30.0)
    except Exception as exc:
        return {"enabled": True, "nodes": [], "error": str(exc)}
    return {
        "enabled": True,
        "role": getattr(st.settings, "cluster_role", ""),
        "nodes": jsonable_encoder(nodes),
    }


# ------------------------------------------------------------------ 思考模式
@router.post("/api/thinking/toggle")
def thinking_toggle(request: Request, payload: dict = Body(...)):
    """POST /api/thinking/toggle → {show: bool}"""
    st = _state(request)
    show = bool(payload.get("show"))
    st.settings.show_thinking = show
    st.persist_settings()
    return {"ok": True, "show_thinking": show}


# ------------------------------------------------------------------ 聚合状态
@router.get("/api/state")
def console_state(request: Request):
    """GET /api/state → 控制台首屏聚合状态（便捷端点，非 §3.10 契约项）。"""
    st = _state(request)

    persona = None
    if st.persona_manager is not None:
        try:
            p = st.persona_manager.get(st.settings.active_persona)
            persona = {
                "id": p.id,
                "display_name": p.display_name,
                "gender": p.gender,
                "traits": list(getattr(p, "traits", []) or []),
                "address_master_as": getattr(p, "address_master_as", "主人"),
            }
        except Exception:
            persona = None

    emotion = None
    if st.emotion is not None:
        try:
            emotion = jsonable_encoder(st.emotion.current())
        except Exception:
            emotion = None

    return {
        "master_name": getattr(st.settings, "master_name", "主人"),
        "persona": persona,
        "emotion": emotion,
        "show_thinking": bool(getattr(st.settings, "show_thinking", True)),
        "settings": jsonable_encoder(st.settings),
        "engine": {"available": st.engine is not None, "error": st.engine_error},
        "voice": voice_status(request),
    }
