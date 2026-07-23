#!/usr/bin/env python3
"""Resume incomplete V2 animation downloads and retry failed tasks once."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

import generate_meshy_v2_characters as pipeline


DEFAULT_PROJECT = (
    pipeline.OUTPUT_ROOT
    / "20260724_025638_qiban-v2-detailed-characters_019f9056"
)


def current_task(
    session: requests.Session,
    task_id: str,
) -> dict:
    return pipeline.request_json(
        session,
        "GET",
        f"/openapi/v1/animations/{task_id}",
        timeout=45,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Allow one 3-credit retry for a failed animation.",
    )
    args = parser.parse_args()
    project_dir = args.project.resolve()
    metadata_path = project_dir / "metadata.json"
    if not metadata_path.exists():
        raise SystemExit(f"ERROR: metadata not found: {metadata_path}")

    pipeline.load_env()
    api_key = os.environ.get("MESHY_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("ERROR: MESHY_API_KEY not set")
    session = requests.Session()
    session.trust_env = False
    session.headers.update({"Authorization": f"Bearer {api_key}"})

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    balance_before_resume = pipeline.get_balance(session)
    print(f"BALANCE_BEFORE_RESUME: {balance_before_resume}", flush=True)
    metadata["balance_before_resume"] = balance_before_resume

    rig_task_ids = {
        item["character"]: item["task_id"]
        for item in metadata["tasks"]
        if item["type"] == "rigging" and item["status"] == "SUCCEEDED"
    }
    pending = [
        item
        for item in list(metadata["tasks"])
        if item["type"] == "animation"
        and item["character"] == "male"
        and not item.get("files")
    ]
    print(f"PENDING_ANIMATIONS: {len(pending)}", flush=True)

    for entry in pending:
        character_id = entry["character"]
        action_name = entry["action"]
        task_id = entry["task_id"]
        task = current_task(session, task_id)
        status = task.get("status")
        print(
            f"RECOVER: {character_id}/{action_name} {task_id[:8]} {status}",
            flush=True,
        )

        if status in {"FAILED", "CANCELED"}:
            pipeline.update_task(project_dir, metadata, task)
            if not args.yes:
                raise SystemExit(
                    f"Retry required for {character_id}/{action_name}; rerun with --yes"
                )
            retry_task_id = pipeline.create_animation_task(
                session,
                character_id,
                rig_task_ids[character_id],
                action_name,
                pipeline.ACTIONS[action_name],
            )
            pipeline.add_task(
                project_dir,
                metadata,
                retry_task_id,
                "animation",
                character_id,
                action_name,
            )
            task_id = retry_task_id

        task = pipeline.poll_task(
            session,
            "/openapi/v1/animations",
            task_id,
            f"resume/{character_id}/{action_name}",
            timeout=720,
        )
        result = pipeline.result_object(task)
        animation_url = result.get("animation_glb_url")
        if not animation_url:
            raise RuntimeError(
                f"Missing animation GLB for {character_id}/{action_name}"
            )
        destination = (
            project_dir
            / pipeline.CHARACTERS[character_id]["slug"]
            / f"{action_name}.glb"
        )
        files = [pipeline.download(session, animation_url, destination)]
        pipeline.update_task(project_dir, metadata, task, files)

    balance_after = pipeline.get_balance(session)
    metadata["balance_after"] = balance_after
    metadata["actual_credits"] = metadata["balance_before"] - balance_after
    metadata["resume_finished_at"] = datetime.now().isoformat()
    pipeline.save_metadata(project_dir, metadata)
    pipeline.record_history(project_dir, metadata)
    print(f"BALANCE_AFTER: {balance_after}", flush=True)
    print(
        f"ACTUAL_CREDITS: {metadata['actual_credits']}",
        flush=True,
    )
    print(f"PROJECT_DIR: {project_dir.relative_to(pipeline.ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
