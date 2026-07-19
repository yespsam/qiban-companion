#!/usr/bin/env python3
"""Generate Meshy animation GLBs for the companion characters."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "meshy_output"
ASSET_ROOT = ROOT / "desktop-wallpaper" / "assets" / "models"
BASE = "https://api.meshy.ai"

CHARACTERS = {
    "female": {
        "display": "小栖",
        "asset_prefix": "xiao-qi",
        "rig_task_id": "019f7595-9be2-74bc-a126-5a0c5ece8ccc",
    },
    "male": {
        "display": "栖安",
        "asset_prefix": "qi-an",
        "rig_task_id": "019f789b-78f1-7300-b5d1-d220f49a9d8c",
    },
}

ACTIONS = {
    "idle": {"action_id": 0, "library_name": "Idle"},
    "nod": {"action_id": 25, "library_name": "Agree_Gesture"},
    "heart": {"action_id": 27, "library_name": "Big_Heart_Gesture"},
    "wave": {"action_id": 28, "library_name": "Big_Wave_Hello"},
    "voice": {"action_id": 56, "library_name": "Stand_and_Chat"},
}


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:36] or "animation"


def request_json(session: requests.Session, method: str, path: str, **kwargs):
    response = session.request(method, f"{BASE}{path}", timeout=kwargs.pop("timeout", 30), **kwargs)
    if response.status_code == 401:
        sys.exit("ERROR: Invalid Meshy API key (401)")
    if response.status_code == 402:
        balance = get_balance(session)
        sys.exit(f"ERROR: Insufficient credits (402). Current balance: {balance}")
    if response.status_code == 429:
        time.sleep(5)
        response = session.request(method, f"{BASE}{path}", timeout=kwargs.pop("timeout", 30), **kwargs)
    response.raise_for_status()
    return response.json()


def get_balance(session: requests.Session):
    data = request_json(session, "GET", "/openapi/v1/balance")
    return data.get("balance", data)


def create_animation(session: requests.Session, rig_task_id: str, action_id: int) -> str:
    data = request_json(
        session,
        "POST",
        "/openapi/v1/animations",
        json={
            "rig_task_id": rig_task_id,
            "action_id": action_id,
            "post_process": {
                "operation_type": "change_fps",
                "fps": 30,
            },
        },
    )
    task_id = data["result"]
    print(f"TASK_CREATED: {task_id} action={action_id}", flush=True)
    return task_id


def poll_animation(session: requests.Session, task_id: str, timeout: int = 360):
    elapsed = 0
    delay = 5
    poll_count = 0
    while elapsed <= timeout:
        poll_count += 1
        task = request_json(session, "GET", f"/openapi/v1/animations/{task_id}", timeout=30)
        status = task["status"]
        progress = int(task.get("progress", 0) or 0)
        print(f"  {task_id[:8]} [{progress:3d}%] {status} ({elapsed}s, poll #{poll_count})", flush=True)
        if status == "SUCCEEDED":
            return task
        if status in ("FAILED", "CANCELED"):
            error = task.get("task_error") or {}
            raise RuntimeError(f"{task_id} {status}: {error.get('message', 'Unknown error')}")
        time.sleep(delay)
        elapsed += delay
        delay = 15 if progress >= 95 else min(int(delay * 1.5), 20)
    raise TimeoutError(f"Timed out waiting for {task_id}")


def download(session: requests.Session, url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {path.relative_to(ROOT)}", flush=True)
    with session.get(url, stream=True, timeout=300) as response:
        response.raise_for_status()
        with path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)
    print(f"DOWNLOADED: {path.relative_to(ROOT)} ({path.stat().st_size / 1024 / 1024:.1f} MB)", flush=True)


def record_history(project_dir: Path, metadata: dict) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    history_path = OUTPUT_ROOT / "history.json"
    if history_path.exists():
        history = json.loads(history_path.read_text(encoding="utf-8"))
    else:
        history = {"version": 1, "projects": []}

    folder = project_dir.name
    entry = next((item for item in history["projects"] if item.get("folder") == folder), None)
    summary = {
        "folder": folder,
        "prompt": "qiban companion custom animations",
        "task_type": "animation",
        "root_task_id": metadata["tasks"][0]["task_id"] if metadata["tasks"] else "",
        "created_at": metadata["created_at"],
        "updated_at": metadata["updated_at"],
        "task_count": len(metadata["tasks"]),
    }
    if entry:
        entry.update(summary)
    else:
        history["projects"].append(summary)
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    load_env_file(ROOT / ".env")
    load_env_file(ROOT / ".env.local")
    api_key = os.environ.get("MESHY_API_KEY")
    if not api_key:
        sys.exit("ERROR: MESHY_API_KEY not set")

    session = requests.Session()
    session.trust_env = False
    session.headers.update({"Authorization": f"Bearer {api_key}"})

    balance_before = get_balance(session)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    project_dir = OUTPUT_ROOT / f"{timestamp}_{slugify('qiban companion animations')}"
    metadata = {
        "project_name": "栖伴 custom Meshy animations",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "balance_before": balance_before,
        "balance_after": None,
        "planned_credits": len(CHARACTERS) * len(ACTIONS) * 3,
        "characters": CHARACTERS,
        "actions": ACTIONS,
        "tasks": [],
    }

    print(f"BALANCE_BEFORE: {balance_before}", flush=True)
    print(f"PLANNED_CREDITS: {metadata['planned_credits']}", flush=True)

    created = []
    for character_id, character in CHARACTERS.items():
        for action_name, action in ACTIONS.items():
            task_id = create_animation(session, character["rig_task_id"], action["action_id"])
            created.append((character_id, action_name, action, task_id))
            metadata["tasks"].append(
                {
                    "task_id": task_id,
                    "character": character_id,
                    "display": character["display"],
                    "action": action_name,
                    "action_id": action["action_id"],
                    "library_name": action["library_name"],
                    "status": "CREATED",
                    "files": [],
                    "created_at": datetime.now().isoformat(),
                }
            )

    downloaded = []
    for character_id, action_name, action, task_id in created:
        task = poll_animation(session, task_id)
        result = task.get("result") or {}
        glb_url = result.get("animation_glb_url")
        if not glb_url:
            raise RuntimeError(f"{task_id} missing animation_glb_url")

        character = CHARACTERS[character_id]
        local_name = f"{character['asset_prefix']}-{action_name}.glb"
        project_file = project_dir / local_name
        asset_file = ASSET_ROOT / local_name
        download(session, glb_url, project_file)
        shutil.copy2(project_file, asset_file)
        downloaded.append(str(asset_file.relative_to(ROOT)))

        for item in metadata["tasks"]:
            if item["task_id"] == task_id:
                item.update(
                    {
                        "status": task["status"],
                        "progress": task.get("progress"),
                        "consumed_credits": task.get("consumed_credits"),
                        "finished_at": task.get("finished_at"),
                        "files": [
                            str(project_file.relative_to(ROOT)),
                            str(asset_file.relative_to(ROOT)),
                        ],
                    }
                )
                break

    balance_after = get_balance(session)
    metadata["balance_after"] = balance_after
    metadata["updated_at"] = datetime.now().isoformat()
    metadata["downloaded"] = downloaded
    record_history(project_dir, metadata)

    print(f"BALANCE_AFTER: {balance_after}", flush=True)
    print(f"PROJECT_DIR: {project_dir.relative_to(ROOT)}", flush=True)
    print("DOWNLOADED_ASSETS:", flush=True)
    for item in downloaded:
        print(f"  - {item}", flush=True)


if __name__ == "__main__":
    main()
