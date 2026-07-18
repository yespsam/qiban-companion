#!/usr/bin/env python3
"""Generate Qiban companion character models with Meshy.

This script intentionally requires --yes before it spends API credits.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "meshy_output"
MODEL_DIR = ROOT / "desktop-wallpaper" / "assets" / "models"
API_BASE = "https://api.meshy.ai"


CHARACTERS: dict[str, dict[str, str]] = {
    "female": {
        "slug": "xiao-qi",
        "name": "小栖",
        "front": "modeling/reference/xiao-qi-front-clean.png",
        "back": "modeling/reference/xiao-qi-back.png",
        "texture_prompt": (
            "High quality anime virtual human girl, not chibi, realistic 7-head "
            "proportions, warm purple-black shoulder length hair with green inner "
            "highlights, black and deep green cyber jacket, white ribbed inner top, "
            "black asymmetric shorts and skirt panel, white ankle boots, gold chain "
            "ornaments, translucent neon green panels, clean game-ready PBR texture."
        ),
    },
    "male": {
        "slug": "qi-an",
        "name": "栖安",
        "front": "modeling/reference/qi-an-front.png",
        "back": "modeling/reference/qi-an-back.png",
        "texture_prompt": (
            "High quality anime virtual human young man, not chibi, realistic "
            "7.5-head proportions, tousled purple-black hair, calm green eyes, "
            "black layered techwear jacket, white high collar shirt, slim black "
            "pants, black boots, green translucent coat panels, gold star ornament "
            "and chain accessories, clean game-ready PBR texture."
        ),
    },
}


def load_dotenv() -> None:
    for name in (".env", ".env.local"):
        path = ROOT / name
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_key() -> str:
    load_dotenv()
    key = os.environ.get("MESHY_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "MESHY_API_KEY not found.\n"
            "Create one at https://www.meshy.ai/settings/api, then run:\n"
            '  export MESHY_API_KEY="msy_your_key_here"'
        )
    return key


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def request_json(method: str, endpoint: str, key: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    import requests

    response = requests.request(
        method,
        f"{API_BASE}{endpoint}",
        headers={"Authorization": f"Bearer {key}"},
        json=payload,
        timeout=60,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {endpoint} failed: HTTP {response.status_code} {response.text[:500]}")
    return response.json()


def poll_task(endpoint: str, task_id: str, key: str) -> dict[str, Any]:
    print(f"Polling {endpoint}/{task_id}")
    while True:
        task = request_json("GET", f"{endpoint}/{task_id}", key)
        status = task.get("status")
        progress = task.get("progress")
        print(f"  status={status} progress={progress}")
        if status == "SUCCEEDED":
            return task
        if status in {"FAILED", "CANCELED"}:
            raise RuntimeError(json.dumps(task.get("task_error") or task, ensure_ascii=False, indent=2))
        time.sleep(6)


def download(url: str, dest: Path) -> None:
    import requests

    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=120) as response:
        response.raise_for_status()
        with dest.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 512):
                if chunk:
                    handle.write(chunk)


def model_urls_from(task: dict[str, Any]) -> dict[str, str]:
    urls = dict(task.get("model_urls") or {})
    if task.get("rigged_character_glb_url"):
        urls["glb"] = task["rigged_character_glb_url"]
    if task.get("rigged_character_fbx_url"):
        urls["fbx"] = task["rigged_character_fbx_url"]
    return urls


def create_character(character_id: str, args: argparse.Namespace, key: str, run_dir: Path) -> None:
    spec = CHARACTERS[character_id]
    slug = spec["slug"]
    char_dir = run_dir / slug
    char_dir.mkdir(parents=True, exist_ok=True)

    front = ROOT / spec["front"]
    if not front.exists():
        raise FileNotFoundError(front)

    payload = {
        "image_url": data_uri(front),
        "ai_model": "meshy-6",
        "topology": "quad",
        "target_polycount": args.polycount,
        "should_texture": True,
        "enable_pbr": True,
        "hd_texture": args.hd_texture,
        "pose_mode": "t-pose",
        "should_remesh": True,
        "target_formats": ["glb", "fbx"],
        "texture_prompt": spec["texture_prompt"],
        "remove_lighting": True,
        "image_enhancement": True,
        "auto_size": True,
        "origin_at": "bottom",
    }

    print(f"\nCreating Image-to-3D task for {spec['name']} ({slug})")
    image_resp = request_json("POST", "/openapi/v1/image-to-3d", key, payload)
    image_task_id = image_resp["result"]
    image_task = poll_task("/openapi/v1/image-to-3d", image_task_id, key)
    final_task = image_task

    if args.rig:
        print(f"\nCreating Auto-Rigging task for {spec['name']} ({slug})")
        rig_resp = request_json(
            "POST",
            "/openapi/v1/rigging",
            key,
            {"input_task_id": image_task_id, "height_meters": 1.68 if character_id == "female" else 1.78},
        )
        rig_task_id = rig_resp["result"]
        final_task = poll_task("/openapi/v1/rigging", rig_task_id, key)

    urls = model_urls_from(final_task)
    if "glb" not in urls:
        raise RuntimeError(f"No GLB URL returned for {slug}: {json.dumps(final_task)[:1000]}")

    glb_path = char_dir / f"{slug}.glb"
    download(urls["glb"], glb_path)
    shutil.copy(glb_path, MODEL_DIR / f"{slug}.glb")
    print(f"Saved {glb_path}")
    print(f"Copied to {MODEL_DIR / f'{slug}.glb'}")

    if "fbx" in urls:
        fbx_path = char_dir / f"{slug}.fbx"
        download(urls["fbx"], fbx_path)
        shutil.copy(fbx_path, MODEL_DIR / f"{slug}.fbx")
        print(f"Saved {fbx_path}")

    metadata = {
        "character": character_id,
        "name": spec["name"],
        "image_task_id": image_task_id,
        "source_front": str(front.relative_to(ROOT)),
        "rigged": args.rig,
        "final_task": final_task,
    }
    (char_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Qiban companion GLB/FBX models with Meshy.")
    parser.add_argument("--characters", nargs="+", choices=sorted(CHARACTERS), default=["female"])
    parser.add_argument("--rig", action="store_true", help="Run Meshy Auto-Rigging after Image-to-3D.")
    parser.add_argument("--polycount", type=int, default=70000)
    parser.add_argument("--hd-texture", action="store_true", help="Request 4K base color texture.")
    parser.add_argument("--yes", action="store_true", help="Actually spend Meshy credits.")
    args = parser.parse_args()

    per_character = 30 + (5 if args.rig else 0)
    total = per_character * len(args.characters)
    print("Meshy generation plan")
    print(f"  characters: {', '.join(args.characters)}")
    print(f"  output: GLB + FBX, copied into desktop-wallpaper/assets/models/")
    print(f"  rigging: {'yes' if args.rig else 'no'}")
    print(f"  estimated credits: {total}")
    print("  generated files will be saved under meshy_output/")

    if not args.yes:
        print("\nDry run only. Add --yes to create API tasks and spend credits.")
        return 0

    key = get_key()
    balance = request_json("GET", "/openapi/v1/balance", key)
    print(f"Meshy balance: {json.dumps(balance, ensure_ascii=False)}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = OUTPUT_ROOT / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_qiban_companions"
    run_dir.mkdir(parents=True, exist_ok=True)
    for character_id in args.characters:
        create_character(character_id, args, key, run_dir)
    print(f"\nDone. Project output: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
