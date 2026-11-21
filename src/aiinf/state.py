import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .paths import STATE_FILE

STAGES = ["init", "planned", "scripted", "clips_generated", "rendered", "validated", "exported"]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_state() -> dict:
    return {"schema_version": 1, "last_stage": "init", "concepts": {}, "updated_at": utcnow(), "history": []}


def load_state(path: Path | None = None) -> dict:
    path = Path(path or STATE_FILE)
    if not path.exists():
        return default_state()
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return default_state()


def save_state(state: dict, path: Path | None = None) -> None:
    path = Path(path or STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utcnow()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2, sort_keys=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def advance(state: dict, concept_id: str, stage: str, detail: dict | None = None) -> dict:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage}")
    rec = state["concepts"].setdefault(concept_id, {"last_stage": "init", "artifacts": {}, "errors": []})
    rec["last_stage"] = stage
    if detail:
        rec["artifacts"].update(detail)
    state["last_stage"] = stage
    state["history"].append({"t": utcnow(), "concept": concept_id, "stage": stage})
    return state


def stage_index(stage: str) -> int:
    return STAGES.index(stage) if stage in STAGES else 0
