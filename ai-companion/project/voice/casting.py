"""声优选角（SPEC §3.7a）。

人格 × 关系身份 → 音色/风格/语速/音调；再按 TA 当下心情叠加情绪韵律微调。

铁律（SPEC §1）：
- 顶层零重依赖，yaml 仅在首次解析时懒加载并缓存；
- voices.yaml 缺失、损坏或条目不全时，一律回退到人格自带音色（persona.voice），
  绝不因配音配置问题让语音功能整体挂掉。
"""
from __future__ import annotations

import re

from core.logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_VOICES_PATH = "config/voices.yaml"

_CACHE: dict[str, dict] = {}

_NUM_RE = re.compile(r"^([+-]?\d+)")


def _load(voices_path: str) -> dict:
    """加载并缓存 voices.yaml；缺失/损坏返回 {}（容错优先）。"""
    if voices_path in _CACHE:
        return _CACHE[voices_path]
    data: dict = {}
    try:
        import yaml  # 懒加载

        with open(voices_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            logger.warning("voices.yaml 顶层不是映射，已忽略：%s", voices_path)
            data = {}
    except FileNotFoundError:
        logger.info("voices.yaml 不存在（%s），回退人格自带音色", voices_path)
    except Exception as exc:  # noqa: BLE001 - 配置容错：任何解析异常都回退
        logger.warning("voices.yaml 解析失败（%s）：%s，回退人格自带音色", voices_path, exc)
        data = {}
    _CACHE[voices_path] = data
    return data


def clear_cache() -> None:
    """清空配置缓存（测试与热重载用）。"""
    _CACHE.clear()


def _num(s: str) -> int:
    m = _NUM_RE.match((s or "").strip())
    return int(m.group(1)) if m else 0


def _add_percent(a: str, b: str) -> str:
    return f"{_num(a) + _num(b):+d}%"


def _add_hz(a: str, b: str) -> str:
    return f"{_num(a) + _num(b):+d}Hz"


def _infer_gender(persona_id: str, gender: str | None = None) -> str:
    if gender in {"female", "male"}:
        return gender
    return "male" if ("male" in persona_id and "female" not in persona_id) else "female"


def resolve_cast(
    persona_id: str,
    relationship_id: str | None = None,
    mood: str | None = None,
    *,
    persona_voice: dict | None = None,
    voices_path: str = DEFAULT_VOICES_PATH,
    archetype: str | None = None,
    gender: str | None = None,
) -> dict:
    """解析当前 人格×关系身份×心情 的配音参数。

    :param persona_id: 人格 id（如 female_companion）。
    :param relationship_id: 关系身份 id（lover/friend/bestie/elder），None 用 default。
    :param mood: TA 当下心情（happy/calm/worried/excited/sleepy/care），用于情绪韵律叠加。
    :param persona_voice: 人格自带 voice 配置（作为最终回退）。
    :param voices_path: voices.yaml 路径（测试可指到临时文件）。
    :return: {"voice","style","rate","pitch"}，四项保证为非空字符串（voice 可能为空串，
             交由引擎自己的默认音色兜底）。
    """
    pv = persona_voice if isinstance(persona_voice, dict) else {}
    fb_voice = str(pv.get("edge_tts_voice", "") or "")
    fb_style = str(pv.get("speaking_style", "") or "")

    data = _load(voices_path)
    cast = (data.get("cast") or {}).get(persona_id) or {}
    entry = cast.get(relationship_id or "") or cast.get("default") or {}

    result = {
        "voice": str(entry.get("edge_tts_voice") or fb_voice or ""),
        "style": str(entry.get("style") or fb_style or ""),
        "rate": str(entry.get("rate") or "+0%"),
        "pitch": str(entry.get("pitch") or "+0Hz"),
    }

    # 声线覆盖（SPEC §3.7b）：整组替换 voice/style/rate/pitch
    if archetype:
        g = _infer_gender(persona_id, gender)
        arch = ((data.get("archetypes") or {}).get(g) or {}).get(archetype)
        if isinstance(arch, dict):
            result["voice"] = str(arch.get("edge_tts_voice") or result["voice"])
            result["style"] = str(arch.get("style") or result["style"])
            result["rate"] = str(arch.get("rate") or "+0%")
            result["pitch"] = str(arch.get("pitch") or "+0Hz")
            result["archetype"] = str(arch.get("name") or archetype)

    prosody = (data.get("emotion_prosody") or {}).get(mood or "")
    if isinstance(prosody, dict):
        result["rate"] = _add_percent(result["rate"], str(prosody.get("rate") or "+0%"))
        result["pitch"] = _add_hz(result["pitch"], str(prosody.get("pitch") or "+0Hz"))

    return result


def list_voice_resources(
    persona_id: str,
    relationship_id: str | None = None,
    *,
    persona_voice: dict | None = None,
    voices_path: str = DEFAULT_VOICES_PATH,
    gender: str | None = None,
) -> list[dict]:
    """列出当前人格可选声线资源。

    返回内容是前端可直接渲染的轻量列表，全部来自 voices.yaml 与人格默认音色；
    不 import TTS 重依赖、不触网。
    """
    g = _infer_gender(persona_id, gender)
    base = resolve_cast(
        persona_id,
        relationship_id,
        persona_voice=persona_voice,
        voices_path=voices_path,
        gender=g,
    )
    resources = [{
        "id": "default",
        "archetype": "",
        "name": "随身份",
        "description": "按当前关系身份自动选择声线",
        "provider": "edge_tts",
        "engine": "edge_tts",
        "voice": base["voice"],
        "style": base["style"],
        "rate": base["rate"],
        "pitch": base["pitch"],
        "gender": g,
        "default": True,
    }]

    data = _load(voices_path)
    for key, entry in (((data.get("archetypes") or {}).get(g) or {}).items()):
        if not isinstance(entry, dict):
            continue
        resources.append({
            "id": key,
            "archetype": key,
            "name": str(entry.get("name") or key),
            "description": str(entry.get("description") or ""),
            "provider": "edge_tts",
            "engine": "edge_tts",
            "voice": str(entry.get("edge_tts_voice") or ""),
            "style": str(entry.get("style") or ""),
            "rate": str(entry.get("rate") or "+0%"),
            "pitch": str(entry.get("pitch") or "+0Hz"),
            "gender": g,
            "default": False,
        })
    return resources


_CLONE_NAMES = {"clone", "gpt_sovits", "gpt-sovits", "sovits"}


def is_clone_engine_name(name: str) -> bool:
    """settings.tts_engine 是否为克隆引擎。"""
    return (name or "").strip().lower() in _CLONE_NAMES


def resolve_clone_ref(persona_id: str, *, voices_path: str = DEFAULT_VOICES_PATH) -> str:
    """查 voices.yaml clone.voices.{persona_id}.ref_audio（上传的声优样本路径）。"""
    data = _load(voices_path)
    voices = (data.get("clone") or {}).get("voices") or {}
    entry = voices.get(persona_id) or {}
    return str(entry.get("ref_audio") or "")


def prosody_kwargs(engine, cast: dict) -> dict:
    """仅当引擎声明支持韵律（supports_prosody）时，把 rate/pitch 作为 kwargs 传出。

    保证旧引擎实现（synthesize 签名无 rate/pitch）不受影响。
    """
    if getattr(engine, "supports_prosody", False):
        return {"rate": cast.get("rate", ""), "pitch": cast.get("pitch", "")}
    return {}
