#!/usr/bin/env python3
"""Generate, rig, and animate the approved Qiban V2 character references."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "meshy_output"
HISTORY_PATH = OUTPUT_ROOT / "history.json"
BASE = "https://api.meshy.ai"

CHARACTERS = {
    "female": {
        "display": "小栖 V2",
        "slug": "xiao-qi-v2",
        "height_meters": 1.68,
        "reference": (
            "desktop-wallpaper/assets/concepts/model-references-v2/"
            "xiao-qi-hd-tpose-v2.png"
        ),
        "texture_prompt": (
            "Premium anime game character, adult young woman, natural warm skin, "
            "violet-black layered hair with emerald underlayer, ivory ribbed top, "
            "dark forest-green and white cropped technical jacket, tailored black "
            "shorts with an asymmetric ivory pleated panel, restrained gold hardware, "
            "translucent green ribbons, structured ivory ankle boots. Preserve clean "
            "facial features, five-finger hands, cloth seams, leather, metal, and "
            "translucent PBR material separation. No baked lighting."
        ),
    },
    "male": {
        "display": "栖安 V2",
        "slug": "qi-an-v2",
        "height_meters": 1.79,
        "reference": (
            "desktop-wallpaper/assets/concepts/model-references-v2/"
            "qi-an-hd-tpose-v2.png"
        ),
        "texture_prompt": (
            "Premium anime game character, adult young man, natural healthy light "
            "skin, refined warm face, violet-black layered short hair, clear green "
            "eyes, charcoal-black and forest-green cropped technical jacket, ivory "
            "high-neck shirt, tailored black trousers, restrained gold and emerald "
            "hardware, narrow translucent green side panels, structured black boots. "
            "Preserve broad natural shoulders, five-finger hands, garment seams, "
            "leather, metal, and translucent PBR material separation. No baked lighting."
        ),
    },
}

ACTIONS = {
    "idle": {"action_id": 0, "library_name": "Idle"},
    "nod": {"action_id": 25, "library_name": "Agree_Gesture"},
    "heart": {"action_id": 27, "library_name": "Big_Heart_Gesture"},
    "wave": {"action_id": 28, "library_name": "Big_Wave_Hello"},
    "voice": {"action_id": 56, "library_name": "Stand_and_Chat"},
}


def load_env() -> None:
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


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def request_json(
    session: requests.Session,
    method: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    response = session.request(
        method,
        f"{BASE}{endpoint}",
        json=payload,
        timeout=timeout,
    )
    if response.status_code == 401:
        raise RuntimeError("Invalid Meshy API key (401)")
    if response.status_code == 402:
        balance = session.get(f"{BASE}/openapi/v1/balance", timeout=15).json()
        raise RuntimeError(f"Insufficient Meshy credits (402): {balance}")
    if response.status_code == 429:
        print("RATE_LIMITED: waiting 12s before retry", flush=True)
        time.sleep(12)
        return request_json(session, method, endpoint, payload, timeout)
    if response.status_code >= 400:
        raise RuntimeError(
            f"{method} {endpoint} failed: HTTP {response.status_code} "
            f"{response.text[:1000]}"
        )
    return response.json()


def get_balance(session: requests.Session) -> int:
    payload = request_json(session, "GET", "/openapi/v1/balance")
    return int(payload.get("balance", 0))


def save_metadata(project_dir: Path, metadata: dict[str, Any]) -> None:
    metadata["updated_at"] = datetime.now().isoformat()
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def record_history(project_dir: Path, metadata: dict[str, Any]) -> None:
    if HISTORY_PATH.exists():
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    else:
        history = {"version": 1, "projects": []}
    summary = {
        "folder": project_dir.name,
        "prompt": "qiban v2 detailed characters",
        "task_type": "image-to-3d-rig-animation",
        "root_task_id": metadata["root_task_id"],
        "created_at": metadata["created_at"],
        "updated_at": metadata["updated_at"],
        "task_count": len(metadata["tasks"]),
    }
    existing = next(
        (item for item in history["projects"] if item.get("folder") == project_dir.name),
        None,
    )
    if existing:
        existing.update(summary)
    else:
        history["projects"].append(summary)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_task(
    project_dir: Path,
    metadata: dict[str, Any],
    task_id: str,
    task_type: str,
    character: str,
    action: str = "",
) -> None:
    metadata["tasks"].append(
        {
            "task_id": task_id,
            "type": task_type,
            "character": character,
            "action": action,
            "status": "CREATED",
            "created_at": datetime.now().isoformat(),
            "files": [],
        }
    )
    save_metadata(project_dir, metadata)
    record_history(project_dir, metadata)


def update_task(
    project_dir: Path,
    metadata: dict[str, Any],
    task: dict[str, Any],
    files: list[str] | None = None,
) -> None:
    task_id = task.get("id") or task.get("task_id")
    entry = next(
        (item for item in metadata["tasks"] if item["task_id"] == task_id),
        None,
    )
    if not entry:
        return
    entry.update(
        {
            "status": task.get("status"),
            "progress": task.get("progress"),
            "consumed_credits": task.get("consumed_credits"),
            "finished_at": task.get("finished_at"),
        }
    )
    if files:
        entry["files"] = files
    save_metadata(project_dir, metadata)
    record_history(project_dir, metadata)


def poll_task(
    session: requests.Session,
    endpoint: str,
    task_id: str,
    label: str,
    timeout: int = 1200,
) -> dict[str, Any]:
    elapsed = 0
    delay = 6
    poll_count = 0
    while elapsed <= timeout:
        poll_count += 1
        task = request_json(session, "GET", f"{endpoint}/{task_id}", timeout=45)
        status = task.get("status", "UNKNOWN")
        progress = int(task.get("progress", 0) or 0)
        print(
            f"{label}: {task_id[:8]} [{progress:3d}%] {status} "
            f"({elapsed}s, poll #{poll_count})",
            flush=True,
        )
        if status == "SUCCEEDED":
            return task
        if status in {"FAILED", "CANCELED"}:
            error = task.get("task_error") or {}
            raise RuntimeError(
                f"{label} {status}: {error.get('message', 'Unknown error')}"
            )
        current_delay = 15 if progress >= 95 else delay
        time.sleep(current_delay)
        elapsed += current_delay
        delay = min(int(delay * 1.45), 25)
    raise TimeoutError(f"Timed out waiting for {label} ({task_id})")


def download(session: requests.Session, url: str, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"DOWNLOADING: {destination.relative_to(ROOT)}", flush=True)
    with session.get(url, stream=True, timeout=300) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    relative = str(destination.relative_to(ROOT))
    print(
        f"DOWNLOADED: {relative} ({destination.stat().st_size / 1024 / 1024:.1f} MB)",
        flush=True,
    )
    return relative


def model_urls(task: dict[str, Any]) -> dict[str, str]:
    urls = dict(task.get("model_urls") or {})
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    for source in (task, result):
        if source.get("rigged_character_glb_url"):
            urls["glb"] = source["rigged_character_glb_url"]
        if source.get("rigged_character_fbx_url"):
            urls["fbx"] = source["rigged_character_fbx_url"]
    return urls


def result_object(task: dict[str, Any]) -> dict[str, Any]:
    result = task.get("result")
    return result if isinstance(result, dict) else {}


def create_image_task(
    session: requests.Session,
    character_id: str,
    spec: dict[str, Any],
) -> str:
    reference = ROOT / spec["reference"]
    if not reference.exists():
        raise FileNotFoundError(reference)
    payload = {
        "image_url": data_uri(reference),
        "ai_model": "meshy-6",
        "topology": "quad",
        "target_polycount": 100000,
        "should_texture": True,
        "enable_pbr": True,
        "hd_texture": True,
        "pose_mode": "t-pose",
        "should_remesh": True,
        "target_formats": ["glb", "fbx"],
        "texture_prompt": spec["texture_prompt"],
        "remove_lighting": True,
        "image_enhancement": True,
        "auto_size": True,
        "origin_at": "bottom",
    }
    response = request_json(
        session,
        "POST",
        "/openapi/v1/image-to-3d",
        payload,
        timeout=120,
    )
    task_id = response["result"]
    print(f"TASK_CREATED: image-to-3d {character_id} {task_id}", flush=True)
    return task_id


def create_rig_task(
    session: requests.Session,
    character_id: str,
    image_task_id: str,
) -> str:
    response = request_json(
        session,
        "POST",
        "/openapi/v1/rigging",
        {
            "input_task_id": image_task_id,
            "height_meters": CHARACTERS[character_id]["height_meters"],
        },
    )
    task_id = response["result"]
    print(f"TASK_CREATED: rigging {character_id} {task_id}", flush=True)
    return task_id


def create_animation_task(
    session: requests.Session,
    character_id: str,
    rig_task_id: str,
    action_name: str,
    action: dict[str, Any],
) -> str:
    response = request_json(
        session,
        "POST",
        "/openapi/v1/animations",
        {
            "rig_task_id": rig_task_id,
            "action_id": action["action_id"],
            "post_process": {
                "operation_type": "change_fps",
                "fps": 30,
            },
        },
    )
    task_id = response["result"]
    print(
        f"TASK_CREATED: animation {character_id}/{action_name} {task_id}",
        flush=True,
    )
    return task_id


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Spend Meshy credits for the approved V2 pipeline.",
    )
    args = parser.parse_args()
    planned_credits = len(CHARACTERS) * (30 + 5 + len(ACTIONS) * 3)
    print(f"PLANNED_CREDITS: {planned_credits}", flush=True)
    print("OUTPUT_ROOT: meshy_output/", flush=True)
    if not args.yes:
        print("Dry run only. Add --yes after user confirmation.", flush=True)
        return 0

    load_env()
    api_key = os.environ.get("MESHY_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ERROR: MESHY_API_KEY not set")
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"Authorization": f"Bearer {api_key}"})

    balance_before = get_balance(session)
    print(f"BALANCE_BEFORE: {balance_before}", flush=True)
    if balance_before < planned_credits:
        raise SystemExit(
            f"ERROR: need {planned_credits} credits, balance is {balance_before}"
        )

    female_task_id = create_image_task(session, "female", CHARACTERS["female"])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_slug = re.sub(r"[^a-z0-9]+", "-", "qiban-v2-detailed-characters")
    project_dir = (
        OUTPUT_ROOT
        / f"{timestamp}_{folder_slug}_{female_task_id[:8]}"
    )
    metadata: dict[str, Any] = {
        "project_name": "栖伴 V2 detailed Meshy characters",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "root_task_id": female_task_id,
        "planned_credits": planned_credits,
        "balance_before": balance_before,
        "balance_after": None,
        "characters": CHARACTERS,
        "actions": ACTIONS,
        "tasks": [],
    }
    add_task(
        project_dir,
        metadata,
        female_task_id,
        "image-to-3d",
        "female",
    )

    image_tasks = {"female": female_task_id}
    male_task_id = create_image_task(session, "male", CHARACTERS["male"])
    image_tasks["male"] = male_task_id
    add_task(
        project_dir,
        metadata,
        male_task_id,
        "image-to-3d",
        "male",
    )

    image_results: dict[str, dict[str, Any]] = {}
    for character_id, task_id in image_tasks.items():
        task = poll_task(
            session,
            "/openapi/v1/image-to-3d",
            task_id,
            f"image-to-3d/{character_id}",
        )
        image_results[character_id] = task
        spec = CHARACTERS[character_id]
        char_dir = project_dir / spec["slug"]
        files: list[str] = []
        urls = model_urls(task)
        if urls.get("glb"):
            files.append(
                download(session, urls["glb"], char_dir / "model.glb")
            )
        thumbnail = task.get("thumbnail_url")
        if thumbnail:
            files.append(
                download(session, thumbnail, char_dir / "thumbnail.png")
            )
        update_task(project_dir, metadata, task, files)

    rig_tasks: dict[str, str] = {}
    for character_id, image_task_id in image_tasks.items():
        rig_task_id = create_rig_task(session, character_id, image_task_id)
        rig_tasks[character_id] = rig_task_id
        add_task(
            project_dir,
            metadata,
            rig_task_id,
            "rigging",
            character_id,
        )

    rig_results: dict[str, dict[str, Any]] = {}
    for character_id, rig_task_id in rig_tasks.items():
        task = poll_task(
            session,
            "/openapi/v1/rigging",
            rig_task_id,
            f"rigging/{character_id}",
        )
        rig_results[character_id] = task
        spec = CHARACTERS[character_id]
        char_dir = project_dir / spec["slug"]
        files: list[str] = []
        urls = model_urls(task)
        if not urls.get("glb"):
            raise RuntimeError(f"Missing rigged GLB for {character_id}")
        files.append(
            download(session, urls["glb"], char_dir / "rigged.glb")
        )
        result = result_object(task)
        basics = (
            result.get("basic_animations")
            if isinstance(result.get("basic_animations"), dict)
            else {}
        )
        for name, key in (
            ("walk", "walking_glb_url"),
            ("run", "running_glb_url"),
        ):
            if basics.get(key):
                files.append(
                    download(
                        session,
                        basics[key],
                        char_dir / f"{name}.glb",
                    )
                )
        update_task(project_dir, metadata, task, files)

    animation_tasks: list[tuple[str, str, str]] = []
    for character_id, rig_task_id in rig_tasks.items():
        for action_name, action in ACTIONS.items():
            task_id = create_animation_task(
                session,
                character_id,
                rig_task_id,
                action_name,
                action,
            )
            animation_tasks.append((character_id, action_name, task_id))
            add_task(
                project_dir,
                metadata,
                task_id,
                "animation",
                character_id,
                action_name,
            )

    for character_id, action_name, task_id in animation_tasks:
        task = poll_task(
            session,
            "/openapi/v1/animations",
            task_id,
            f"animation/{character_id}/{action_name}",
            timeout=720,
        )
        result = result_object(task)
        animation_url = result.get("animation_glb_url")
        if not animation_url:
            raise RuntimeError(
                f"Missing animation GLB for {character_id}/{action_name}"
            )
        spec = CHARACTERS[character_id]
        file_path = project_dir / spec["slug"] / f"{action_name}.glb"
        files = [download(session, animation_url, file_path)]
        update_task(project_dir, metadata, task, files)

    balance_after = get_balance(session)
    metadata["balance_after"] = balance_after
    metadata["actual_credits"] = balance_before - balance_after
    save_metadata(project_dir, metadata)
    record_history(project_dir, metadata)
    print(f"BALANCE_AFTER: {balance_after}", flush=True)
    print(f"ACTUAL_CREDITS: {balance_before - balance_after}", flush=True)
    print(f"PROJECT_DIR: {project_dir.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
