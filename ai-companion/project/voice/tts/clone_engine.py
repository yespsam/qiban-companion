"""本地语音克隆引擎（SPEC §3.7a）：把 TA 的声音换成你上传的声优样本。

协议兼容 GPT-SoVITS api.py（默认 http://127.0.0.1:9880/tts，GET 返回音频流）。
使用步骤：
  1. 本地部署 GPT-SoVITS 并启动 api.py（或兼容服务）；
  2. 上传 3~10 秒干净人声参考音频：POST /api/voice/upload（或手动配置
     settings.yaml 的 clone_ref_audio / clone_ref_text）；
  3. settings.yaml 设置 tts_engine: clone。

铁律（SPEC §1）：httpx 仅在 synthesize() 内懒加载；构造不触网。
"""
from __future__ import annotations

import os

from core.logging_utils import get_logger
from voice.tts.base import TTSDependencyError, TTSEngine, TTSError

logger = get_logger(__name__)

INSTALL_HINT = "httpx 未安装。请执行：pip install httpx"
NO_REF_HINT = (
    "未配置克隆参考音频。请先上传声优样本：POST /api/voice/upload（3~10 秒干净人声），"
    "或在 settings.yaml 中配置 clone_ref_audio / clone_ref_text"
)


class CloneTTSEngine(TTSEngine):
    """GPT-SoVITS 兼容的 HTTP 克隆 TTS。"""

    name = "clone"
    output_ext = ".wav"

    def __init__(self, api_base: str = "http://127.0.0.1:9880",
                 ref_audio: str = "", ref_text: str = "", timeout: float = 60.0):
        self.api_base = (api_base or "http://127.0.0.1:9880").rstrip("/")
        self.ref_audio = ref_audio or ""
        self.ref_text = ref_text or ""
        self.timeout = timeout

    def synthesize(self, text: str, voice: str, out_path: str, style: str = "",
                   rate: str = "", pitch: str = "") -> str:
        if not text or not text.strip():
            raise TTSError("克隆 TTS 收到空文本，无法合成")
        # voice 参数若是存在的音频路径，则当成本轮参考音频（支持按人格切换声优）
        ref = voice if (voice and os.path.exists(voice)) else self.ref_audio
        if not ref:
            raise TTSError(NO_REF_HINT)
        try:
            import httpx  # 懒加载（SPEC §1）
        except ImportError as exc:
            raise TTSDependencyError(INSTALL_HINT) from exc
        params = {
            "text": text,
            "text_lang": "zh",
            "ref_audio_path": ref,
            "prompt_lang": "zh",
            "prompt_text": self.ref_text or "主人，你好。",
        }
        try:
            resp = httpx.get(f"{self.api_base}/tts", params=params, timeout=self.timeout)
            resp.raise_for_status()
        except TTSError:
            raise
        except Exception as exc:  # 连接失败/服务异常统一包装
            raise TTSError(
                f"克隆 TTS 请求失败（{self.api_base}）：{exc}。"
                "请确认 GPT-SoVITS api.py 已启动且地址正确"
            ) from exc
        with open(out_path, "wb") as f:
            f.write(resp.content)
        logger.info("克隆 TTS 合成完成：%s（ref=%s）", out_path, ref)
        return out_path
