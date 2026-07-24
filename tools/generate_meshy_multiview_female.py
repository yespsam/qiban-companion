#!/usr/bin/env python3
"""Generate and rig the Qiban female character from four orthographic views."""

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
ENDPOINTS = {
    "model": "/openapi/v1/multi-image-to-3d",
    "rig": "/openapi/v1/rigging",
}
REFERENCE_DIR = (
    ROOT
    / "desktop-wallpaper/assets/concepts/model-references-v3/xiao-qi-turnaround"
)
HEAD_REFERENCE_DIR = (
    ROOT
    / "desktop-wallpaper/assets/concepts/model-references-v3/"
    "xiao-qi-head-turnaround"
)
REFERENCE_NAMES = ("front.png", "left.png", "right.png", "back.png")


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
    timeout: int = 120,
) -> dict[str, Any]:
    response = session.request(
        method,
        f"{BASE}{endpoint}",
        json=payload,
        timeout=timeout,
    )
    if response.status_code == 429:
        print("RATE_LIMITED: waiting 12 seconds", flush=True)
        time.sleep(12)
        return request_json(session, method, endpoint, payload, timeout)
    if response.status_code >= 400:
        raise RuntimeError(
            f"{method} {endpoint} failed: HTTP {response.status_code} "
            f"{response.text[:1200]}"
        )
    return response.json()


def get_balance(session: requests.Session) -> int:
    return int(
        request_json(session, "GET", "/openapi/v1/balance").get("balance", 0)
    )


def poll_task(
    session: requests.Session,
    endpoint: str,
    task_id: str,
    label: str,
    timeout: int = 1500,
) -> dict[str, Any]:
    elapsed = 0
    delay = 6
    while elapsed <= timeout:
        task = request_json(session, "GET", f"{endpoint}/{task_id}", timeout=45)
        status = task.get("status", "UNKNOWN")
        progress = int(task.get("progress", 0) or 0)
        print(
            f"{label}: {task_id[:8]} [{progress:3d}%] {status} ({elapsed}s)",
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


def download(
    session: requests.Session,
    url: str,
    destination: Path,
) -> str:
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
        f"DOWNLOADED: {relative} "
        f"({destination.stat().st_size / 1024 / 1024:.1f} MB)",
        flush=True,
    )
    return relative


def write_metadata(project_dir: Path, metadata: dict[str, Any]) -> None:
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
        "prompt": metadata.get(
            "prompt",
            "qiban female exact multiview character",
        ),
        "task_type": metadata.get(
            "task_type",
            "multi-image-to-3d-rig",
        ),
        "root_task_id": metadata["root_task_id"],
        "created_at": metadata["created_at"],
        "updated_at": metadata["updated_at"],
        "task_count": len(metadata["tasks"]),
    }
    previous = next(
        (
            item
            for item in history["projects"]
            if item.get("folder") == project_dir.name
        ),
        None,
    )
    if previous:
        previous.update(summary)
    else:
        history["projects"].append(summary)
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def model_urls(task: dict[str, Any]) -> dict[str, str]:
    urls = dict(task.get("model_urls") or {})
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    if result.get("rigged_character_glb_url"):
        urls["glb"] = result["rigged_character_glb_url"]
    if result.get("rigged_character_fbx_url"):
        urls["fbx"] = result["rigged_character_fbx_url"]
    return urls


def download_model_outputs(
    session: requests.Session,
    task: dict[str, Any],
    character_dir: Path,
    stem: str,
) -> list[str]:
    files: list[str] = []
    urls = model_urls(task)
    for format_name in ("glb", "fbx"):
        if urls.get(format_name):
            files.append(
                download(
                    session,
                    urls[format_name],
                    character_dir / f"{stem}.{format_name}",
                )
            )
    thumbnail = task.get("thumbnail_url")
    if thumbnail:
        files.append(
            download(session, thumbnail, character_dir / f"{stem}-thumbnail.png")
        )
    return files


def run_model(session: requests.Session) -> Path:
    references = [REFERENCE_DIR / name for name in REFERENCE_NAMES]
    missing = [path for path in references if not path.exists()]
    if missing:
        raise FileNotFoundError(", ".join(str(path) for path in missing))

    balance_before = get_balance(session)
    print(f"BALANCE_BEFORE: {balance_before}", flush=True)
    if balance_before < 30:
        raise RuntimeError(f"Need 30 credits, balance is {balance_before}")

    payload = {
        "image_urls": [data_uri(path) for path in references],
        "ai_model": "meshy-6",
        "topology": "quad",
        "target_polycount": 150000,
        "should_remesh": True,
        "save_pre_remeshed_model": True,
        "should_texture": True,
        "enable_pbr": True,
        "hd_texture": True,
        "pose_mode": "t-pose",
        "texture_prompt": (
            "Exact premium anime game character from the four orthographic "
            "references. Preserve the same adult female face, refined brown-violet "
            "anime eyes, small natural nose and mouth, pointed jaw, violet-black "
            "layered hair with emerald underlayer and the exact gold-green hair "
            "ornament. Preserve the ivory ribbed top, forest-green and white "
            "technical jacket, black tailored shorts, asymmetric ivory pleated "
            "panel, gold hardware, translucent green ribbons, leg strap, five "
            "fingers, socks, and ivory boots. Clean PBR material separation, no "
            "baked lighting, no face mask, no flat billboard."
        ),
        "remove_lighting": True,
        "image_enhancement": False,
        "multi_view_thumbnails": True,
        "target_formats": ["glb", "fbx"],
        "auto_size": True,
        "origin_at": "bottom",
    }
    response = request_json(
        session,
        "POST",
        ENDPOINTS["model"],
        payload,
        timeout=180,
    )
    task_id = response["result"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", "qiban-female-exact-multiview")
    project_dir = OUTPUT_ROOT / f"{timestamp}_{slug}_{task_id[:8]}"
    metadata: dict[str, Any] = {
        "project_name": "栖伴 female exact multiview V3",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "root_task_id": task_id,
        "planned_credits": 35,
        "balance_before": balance_before,
        "balance_after_model": None,
        "balance_after_rig": None,
        "references": [
            str(path.relative_to(ROOT))
            for path in references
        ],
        "tasks": [
            {
                "task_id": task_id,
                "type": "multi-image-to-3d",
                "status": "CREATED",
                "created_at": datetime.now().isoformat(),
                "files": [],
            }
        ],
    }
    write_metadata(project_dir, metadata)
    record_history(project_dir, metadata)
    print(f"TASK_CREATED: multi-image-to-3d {task_id}", flush=True)
    print(f"PROJECT_DIR: {project_dir.relative_to(ROOT)}", flush=True)

    task = poll_task(
        session,
        ENDPOINTS["model"],
        task_id,
        "multi-image-to-3d/female",
    )
    files = download_model_outputs(
        session,
        task,
        project_dir / "xiao-qi-v3",
        "model",
    )
    metadata["tasks"][0].update(
        {
            "status": task.get("status"),
            "progress": task.get("progress"),
            "consumed_credits": task.get("consumed_credits"),
            "finished_at": task.get("finished_at"),
            "files": files,
        }
    )
    balance_after = get_balance(session)
    metadata["balance_after_model"] = balance_after
    metadata["actual_model_credits"] = balance_before - balance_after
    write_metadata(project_dir, metadata)
    record_history(project_dir, metadata)
    print(f"BALANCE_AFTER_MODEL: {balance_after}", flush=True)
    print(f"ACTUAL_MODEL_CREDITS: {balance_before - balance_after}", flush=True)
    return project_dir


def run_head(session: requests.Session) -> Path:
    references = [HEAD_REFERENCE_DIR / name for name in REFERENCE_NAMES]
    missing = [path for path in references if not path.exists()]
    if missing:
        raise FileNotFoundError(", ".join(str(path) for path in missing))

    balance_before = get_balance(session)
    print(f"BALANCE_BEFORE: {balance_before}", flush=True)
    if balance_before < 30:
        raise RuntimeError(f"Need 30 credits, balance is {balance_before}")

    payload = {
        "image_urls": [data_uri(path) for path in references],
        "ai_model": "meshy-6",
        "topology": "quad",
        "target_polycount": 120000,
        "should_remesh": True,
        "save_pre_remeshed_model": True,
        "should_texture": True,
        "enable_pbr": True,
        "hd_texture": True,
        "texture_prompt": (
            "Exact premium 3D anime head and straight neck from the four "
            "orthographic close-up references. Preserve the same adult female "
            "identity, face proportions, large refined grey-violet eyes, small "
            "natural nose, closed lips, pointed jaw, ears, and smooth skin. "
            "Preserve the exact opaque layered plum-black hairstyle, violet "
            "sheen, emerald inner hair panels, crown part, flyaway loops, and "
            "the single gold-green ornament on her left side. Preserve only "
            "the ivory and green collar shown in the references. Clean game "
            "character topology and PBR material separation. No shoulders, "
            "torso, duplicate features, holes, flat billboard, mask, or baked "
            "lighting."
        ),
        "remove_lighting": True,
        "image_enhancement": False,
        "multi_view_thumbnails": True,
        "target_formats": ["glb", "fbx"],
        "auto_size": True,
        "origin_at": "bottom",
    }
    response = request_json(
        session,
        "POST",
        ENDPOINTS["model"],
        payload,
        timeout=180,
    )
    task_id = response["result"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = "qiban-female-exact-head"
    project_dir = OUTPUT_ROOT / f"{timestamp}_{slug}_{task_id[:8]}"
    metadata: dict[str, Any] = {
        "project_name": "栖伴 female exact head V1",
        "prompt": "qiban female exact multiview head",
        "task_type": "multi-image-to-3d-head",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "root_task_id": task_id,
        "planned_credits": 30,
        "balance_before": balance_before,
        "balance_after_model": None,
        "references": [
            str(path.relative_to(ROOT))
            for path in references
        ],
        "tasks": [
            {
                "task_id": task_id,
                "type": "multi-image-to-3d-head",
                "status": "CREATED",
                "created_at": datetime.now().isoformat(),
                "files": [],
            }
        ],
    }
    write_metadata(project_dir, metadata)
    record_history(project_dir, metadata)
    print(f"TASK_CREATED: multi-image-to-3d-head {task_id}", flush=True)
    print(f"PROJECT_DIR: {project_dir.relative_to(ROOT)}", flush=True)

    task = poll_task(
        session,
        ENDPOINTS["model"],
        task_id,
        "multi-image-to-3d/head",
    )
    files = download_model_outputs(
        session,
        task,
        project_dir / "xiao-qi-head-v1",
        "model",
    )
    metadata["tasks"][0].update(
        {
            "status": task.get("status"),
            "progress": task.get("progress"),
            "consumed_credits": task.get("consumed_credits"),
            "finished_at": task.get("finished_at"),
            "files": files,
        }
    )
    balance_after = get_balance(session)
    metadata["balance_after_model"] = balance_after
    metadata["actual_model_credits"] = balance_before - balance_after
    write_metadata(project_dir, metadata)
    record_history(project_dir, metadata)
    print(f"BALANCE_AFTER_MODEL: {balance_after}", flush=True)
    print(f"ACTUAL_MODEL_CREDITS: {balance_before - balance_after}", flush=True)
    return project_dir


def run_rig(session: requests.Session, project_dir: Path) -> Path:
    metadata_path = project_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    model_task_id = metadata["root_task_id"]
    balance_before = get_balance(session)
    print(f"BALANCE_BEFORE_RIG: {balance_before}", flush=True)
    if balance_before < 5:
        raise RuntimeError(f"Need 5 credits, balance is {balance_before}")

    response = request_json(
        session,
        "POST",
        ENDPOINTS["rig"],
        {
            "input_task_id": model_task_id,
            "height_meters": 1.68,
        },
    )
    task_id = response["result"]
    entry = {
        "task_id": task_id,
        "type": "rigging",
        "status": "CREATED",
        "created_at": datetime.now().isoformat(),
        "files": [],
    }
    metadata["tasks"].append(entry)
    write_metadata(project_dir, metadata)
    record_history(project_dir, metadata)
    print(f"TASK_CREATED: rigging {task_id}", flush=True)

    task = poll_task(
        session,
        ENDPOINTS["rig"],
        task_id,
        "rigging/female",
    )
    character_dir = project_dir / "xiao-qi-v3"
    files = download_model_outputs(
        session,
        task,
        character_dir,
        "rigged",
    )
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
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
                    character_dir / f"{name}.glb",
                )
            )
    entry.update(
        {
            "status": task.get("status"),
            "progress": task.get("progress"),
            "consumed_credits": task.get("consumed_credits"),
            "finished_at": task.get("finished_at"),
            "files": files,
        }
    )
    balance_after = get_balance(session)
    metadata["balance_after_rig"] = balance_after
    metadata["actual_rig_credits"] = balance_before - balance_after
    metadata["actual_total_credits"] = (
        metadata.get("balance_before", balance_before) - balance_after
    )
    write_metadata(project_dir, metadata)
    record_history(project_dir, metadata)
    print(f"BALANCE_AFTER_RIG: {balance_after}", flush=True)
    print(f"ACTUAL_RIG_CREDITS: {balance_before - balance_after}", flush=True)
    return project_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("model", "head", "rig"))
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Spend the Meshy credits already confirmed by the user.",
    )
    args = parser.parse_args()
    if not args.yes:
        print("Dry run only. Add --yes after user confirmation.", flush=True)
        return 0
    if args.phase == "rig" and not args.project_dir:
        parser.error("--project-dir is required for the rig phase")

    load_env()
    api_key = os.environ.get("MESHY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MESHY_API_KEY is not configured")
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"Authorization": f"Bearer {api_key}"})

    if args.phase == "model":
        project_dir = run_model(session)
    elif args.phase == "head":
        project_dir = run_head(session)
    else:
        project_dir = args.project_dir
        if not project_dir.is_absolute():
            project_dir = ROOT / project_dir
        run_rig(session, project_dir)
    print(f"DONE: {project_dir.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
