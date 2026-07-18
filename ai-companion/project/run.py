#!/usr/bin/env python3
"""栖伴 入口。
用法：
  python run.py --ui web [--host 127.0.0.1] [--port 7860]   # Web 控制台
  python run.py --ui cli                                    # 终端文字对话
"""
import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="栖伴 本地 AI 情感伴侣")
    parser.add_argument("--ui", choices=["web", "cli"], default="web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()

    from core.config import load_settings  # 懒加载
    settings = load_settings()

    if args.ui == "web":
        import uvicorn
        from ui.app import create_app
        uvicorn.run(create_app(settings), host=args.host, port=args.port)
    else:
        from core.persona import PersonaManager
        from core.memory import MemoryStore
        from core.emotion import EmotionTracker
        from core.engine import CompanionEngine
        from core.llm import create_backend
        backend = create_backend(settings)
        engine = CompanionEngine(
            settings, backend, PersonaManager(),
            MemoryStore(f"{settings.data_dir}/memory.db"),
            EmotionTracker(f"{settings.data_dir}/emotion.json"),
        )
        print("已进入 CLI 对话（输入 exit 退出）")
        while True:
            try:
                text = input("主人: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if text.lower() in {"exit", "quit"}:
                break
            result = engine.chat(text)
            if settings.show_thinking and result.thinking:
                print(f"[内心] {result.thinking}")
            print(f"{result.persona_id}: {result.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
