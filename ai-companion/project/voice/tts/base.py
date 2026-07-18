"""TTS 引擎抽象（SPEC §3.7）。

铁律（SPEC §1）：本模块顶层只允许轻量 import；
edge-tts / piper 等重依赖一律在具体引擎的方法内部懒加载。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.logging_utils import get_logger

logger = get_logger(__name__)


class TTSError(RuntimeError):
    """TTS 合成失败的统一基异常。"""


class TTSDependencyError(TTSError):
    """TTS 可选依赖缺失。异常信息中必须附带安装指引。"""


class TTSEngine(ABC):
    """TTS 引擎抽象（SPEC §3.7）。

    实现约定：
    - 构造方法不得 import 重依赖、不得访问网络/硬件；
    - 重依赖只在 synthesize() 内部懒加载；
    - synthesize() 失败抛 TTSError（或其子类），信息须可指导主人修复。
    """

    #: 引擎名（用于日志与工厂注册）
    name: str = "abstract"
    #: 合成产物扩展名（供 pipeline 决定临时文件名与播放器选择）
    output_ext: str = ".wav"
    #: 是否支持语速/音调韵律微调（SPEC §3.7a）。支持时调用方才传 rate/pitch。
    supports_prosody: bool = False

    @abstractmethod
    def synthesize(self, text: str, voice: str, out_path: str, style: str = "",
                   rate: str = "", pitch: str = "") -> str:
        """把 text 合成为音频文件写入 out_path，返回音频路径。

        :param text: 要合成的文本。
        :param voice: 引擎相关的音色名（edge-tts 为 zh-CN-XiaoyiNeural 之类）。
        :param out_path: 输出音频文件路径。
        :param style: 说话风格提示（如 gentle），引擎尽力而为，可忽略。
        :param rate: 语速微调（如 "-12%"），仅 supports_prosody=True 时传入，可忽略。
        :param pitch: 音调微调（如 "+2Hz"），仅 supports_prosody=True 时传入，可忽略。
        :return: 音频文件路径（通常等于 out_path）。
        """
        raise NotImplementedError
