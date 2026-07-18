#!/usr/bin/env python3
"""按档位下载本地模型（GGUF）。
用法：
  python installer/download_model.py            # 按 settings.yaml 的 tier
  python installer/download_model.py --tier lite
优先使用 huggingface_hub 下载；若后端配置为 ollama，则提示 ollama pull。
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=["lite", "standard", "pro"], default=None)
    args = parser.parse_args()

    import yaml
    settings = yaml.safe_load((ROOT / "config/settings.yaml").read_text(encoding="utf-8"))
    models_cfg = yaml.safe_load((ROOT / "config/models.yaml").read_text(encoding="utf-8"))

    tier = args.tier or settings.get("tier", "standard")
    model_id = models_cfg["tiers"][tier]["model_id"]
    model = models_cfg["models"][model_id]
    dest = ROOT / "data" / "models"
    dest.mkdir(parents=True, exist_ok=True)

    print(f"档位: {tier}  模型: {model_id}")
    print(f"来源: {model['repo']} / {model['file']}")

    if settings.get("llm_backend") == "ollama" and model.get("ollama_tag"):
        print(f"当前后端为 ollama，请执行:  ollama pull {model['ollama_tag']}")
        return 0

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("正在安装 huggingface_hub ...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
        from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id=model["repo"], filename=model["file"],
        local_dir=str(dest / model_id),
    )
    print(f"下载完成: {path}")
    print("请将 settings.yaml 的 llm_backend 改为 llamacpp，并用 llama-server 加载该文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
