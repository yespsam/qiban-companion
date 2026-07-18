"""配置加载（SPEC §3.1）。

从 config/settings.yaml 读取主配置为 Settings dataclass；
save_settings 将其写回（round-trip 安全）。

环境变量 HERMES_HOME：若设置且 data_dir 为相对路径，则数据目录重定位到
$HERMES_HOME/<data_dir>（SPEC §1：运行时数据默认写到项目内 data/）。
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields

import yaml

from core.logging_utils import get_logger

log = get_logger(__name__)


@dataclass
class Settings:
    tier: str = "standard"            # "lite" | "standard" | "pro"
    app_name: str = "栖伴"             # 对用户展示的产品名
    female_name: str = "小栖"          # 女声伴侣展示名
    male_name: str = "栖安"            # 男声伴侣展示名
    llm_backend: str = "mock"         # "llamacpp" | "ollama" | "mock"
    model_id: str = "hermes-3-8b"     # 对应 config/models.yaml 的 key
    llm_temperature: float = 0.72      # 情感伴侣默认略有温度，但不过度发散
    llm_max_tokens: int = 900          # 控制回复长度，避免情绪对话拖成长篇
    conversation_style: str = "voice_first_companion"  # 声音驱动的人格表达模式
    show_thinking: bool = True        # 思考模式：是否把推理链展示给主人
    master_name: str = "主人"
    active_persona: str = "female_companion"
    active_relationship: str = "lover"  # 关系身份：lover | friend | bestie | elder（SPEC §3.2a）
    active_archetype: str = ""          # 声线：女 loli/yujie/funny，男 shonen/uncle/funny（SPEC §3.7b，空=随身份）
    voice_enabled: bool = True
    tts_engine: str = "edge_tts"      # "edge_tts" | "piper" | "clone"
    clone_api_base: str = "http://127.0.0.1:9880"  # 克隆引擎 HTTP API（GPT-SoVITS api.py，SPEC §3.7a）
    clone_ref_audio: str = ""         # 克隆参考音频（/api/voice/upload 上传后自动写入）
    clone_ref_text: str = ""          # 参考音频对应文本
    voice_profile: str = "warm_intimate"  # 语音设计基调：warm_intimate | calm_mature | playful
    visual_style: str = "voice_shaped_virtual_human"  # 首屏虚拟人物造型策略
    stt_model_size: str = "small"     # faster-whisper 规格
    bluetooth_enabled: bool = False
    mihome_enabled: bool = False
    mihome_mode: str = "lan"          # "lan" | "cloud"
    cluster_enabled: bool = False
    cluster_role: str = "master"      # "master" | "worker"
    data_dir: str = "data"


_FIELD_NAMES = {f.name for f in fields(Settings)}


def load_settings(path: str = "config/settings.yaml") -> Settings:
    """从 yaml 加载 Settings。缺失字段用默认值，未知字段忽略（记日志）。"""
    data: dict = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        log.warning("配置文件 %s 不存在，使用默认配置", path)
    if not isinstance(data, dict):
        log.warning("配置文件 %s 内容不是 mapping，使用默认配置", path)
        data = {}

    unknown = set(data) - _FIELD_NAMES
    if unknown:
        log.warning("配置文件含未知字段，已忽略: %s", sorted(unknown))
    kwargs = {k: v for k, v in data.items() if k in _FIELD_NAMES}
    settings = Settings(**kwargs)

    home = os.environ.get("HERMES_HOME")
    if home and not os.path.isabs(settings.data_dir):
        settings.data_dir = os.path.join(home, settings.data_dir)
    return settings


def save_settings(s: Settings, path: str = "config/settings.yaml") -> None:
    """把 Settings 写回 yaml（保留全部契约字段）。"""
    payload = asdict(s)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, allow_unicode=True, sort_keys=False)
