"""栖伴 Web 控制台（FastAPI + 原生前端，无构建步骤）。

对外暴露 ``create_app(settings)``（懒导入，避免顶层引入 FastAPI/core）。
"""

__all__ = ["create_app"]


def __getattr__(name: str):  # PEP 562：懒导出，保持模块顶层轻量
    if name == "create_app":
        from ui.app import create_app

        return create_app
    raise AttributeError(f"module 'ui' has no attribute {name!r}")
