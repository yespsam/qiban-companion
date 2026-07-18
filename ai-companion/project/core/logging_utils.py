"""统一日志：所有模块通过 get_logger(name) 获取 logger。"""
import logging
import sys

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_initialized = False


def get_logger(name: str) -> logging.Logger:
    global _initialized
    if not _initialized:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(_FORMAT))
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        if not root.handlers:
            root.addHandler(handler)
        _initialized = True
    return logging.getLogger(name)
