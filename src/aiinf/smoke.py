"""Kling 3.0 Omni live smoke test.

Issues EXACTLY ONE paid create-task request, polls that single task, downloads the
result into smokes/, validates it, and stops. It never renders, never exports a
production video, never touches clips/ or renders/, and never writes production
pipeline state.

Reuses the existing aiinf.kling client (same endpoint, same auth, same payload
builder). No second API client exists in this module.
"""
import json
import time
from pathlib import Path

from . import assets, kling, reference, validate
from .character import load_character
from .env import load_kling_config
from .paths import SMOKES
from .planner import plan_concepts

SMOKE_DURATION = 5
SMOKE_RESOLUTION = "1080p"
SMOKE_ASPECT_RATIO = "9:16"
SMOKE_AUDIO = "off"

CONFIRMATION = "ABOUT TO MAKE EXACTLY ONE KLING CREATE REQUEST."


def _concept():
    """Deterministic Zyra Rex concept used for the smoke request."""
    return plan_concepts(lane="evergreen", n_per_lane=1)[0]


def reference_status(character: dict | None = None) -> dict:
    """Report whether a Zyra Rex reference image is actually attached.

    Never fabricates a path, URL or Element ID. When the configured image is
    absent the status explicitly says the request carries NO reference.
    """
    character = character or load_character()
    return reference.resolve(character)


def _reference_arg(status: dict) -> dict:
    """Build the payload kwargs for the configured reference, if usable."""
    if not status.get("attached"):
        return {}
    role = status.get("role", "refer_image")
    data_uri = reference.to_data_uri(status["path"])
    key = "first_frame_url" if role == "first_frame" else "refer_image_url"
    return {key: data_uri}


def _redacted(config) -> dict:
    """Config summary safe to print: never include any secret material."""
    if config.api_key and not (config.access_key and config.secret_key):
        auth_mode = "api_key"
    elif config.access_key and config.secret_key:
        auth_mode = "ak_sk_jwt"
    else:
        auth_mode = "none"
    return {
        "base_url": config.base_url,
        "endpoint": kling.CREATE_ENDPOINT,
        "auth_mode": auth_mode,
        "credential_present": config.configured,
        "live_authorized": config.live_authorized,
        "api_key_value": "<redacted>" if config.api_key else None,
    }


def _plan(env) -> tuple:
    """Build the exact request that would be sent. Makes NO network call."""
    config = load_kling_config(env)
    character = load_character()
    concept = _concept()
    ref = reference_status(character)
    payload = kling.build_request_payload(
        concept, 0, duration=SMOKE_DURATION,
        resolution=SMOKE_RESOLUTION, aspect_ratio=SMOKE_ASPECT_RATIO,
        audio=SMOKE_AUDIO,
        **_reference_arg(ref),
    )
    plan = {
        "concept_id": concept.id,
        "concept_role": "prompt source only; no production state or artifacts are touched",
        "character": character["name"],
        "create_url": config.base_url.rstrip("/") + kling.CREATE_ENDPOINT,
        "request_body": payload,
        "config": _redacted(config),
        "output_dir": str(SMOKES),
        "max_create_requests": 1,
        "character_reference": _describe_reference(ref),
    }
    return config, plan


def preview(env=None) -> dict:
    """Build and return the exact request that would be sent. Makes NO network call."""
    _, plan = _plan(env)
    plan["mode"] = "dry-run (no Kling request will be made)"
    if not plan["config"]["credential_present"]:
        plan["note"] = ("credentials NOT present in this environment; "
                        "the live request would be refused until they are set")
    elif not plan["config"]["live_authorized"]:
        plan["note"] = ("credentials present but live not authorized; "
                        "set KLING_LIVE_AUTHORIZED=1 or the run would be refused")
    return plan


def _describe_reference(ref: dict) -> dict:
    """Human-readable, non-fabricating summary of reference attachment."""
    if not ref.get("attached"):
        return {
            "attached": False,
            "summary": "NO Zyra Rex reference attached to this request (prompt-only)",
            "reason": ref.get("reason", "unknown"),
            "configured_path": ref.get("configured_path"),
        }
    return {
        "attached": True,
        "summary": (f"Zyra Rex reference attached as contents[type={ref['role']}] "
                    f"via inline base64 ({ref['width']}x{ref['height']}, {ref['bytes']} bytes)"),
        "role": ref["role"],
        "dimensions": f"{ref['width']}x{ref['height']}",
        "bytes": ref["bytes"],
        "transport": "inline base64 data URI (no external upload)",
    }


def _check_config(config):
    if not config.configured:
        raise kling.KlingError("no Kling credentials configured (KLING_API_KEY or KLING_ACCESS_KEY+KLING_SECRET_KEY)")
    if config.mock:
        raise kling.KlingError("KLING_MOCK=1 set; refusing a paid smoke test")
    if not config.can_call_live:
        raise kling.KlingError("live not authorized; set KLING_LIVE_AUTHORIZED=1 to allow the paid smoke test")


def run_smoke_test(confirm: bool = False, env=None, poll_interval: float = 10.0,
                   poll_timeout: float = 900.0) -> dict:
    """Perform the single-request live smoke test. Requires ``confirm=True``."""
    config, plan = _plan(env)
    concept = _concept()  # get concept separately since _plan doesn't return it
    if not confirm:
        plan["mode"] = "dry-run (no Kling request will be made)"
        if not config.configured:
            plan["note"] = ("credentials NOT present in this environment; "
                            "the live request would be refused until they are set")
        elif not config.can_call_live:
            plan["note"] = ("credentials present but live not authorized; "
                            "set KLING_LIVE_AUTHORIZED=1 or the run would be refused")
        return plan

    _check_config(config)

    plan["mode"] = "live"
    plan["confirmation"] = CONFIRMATION
    SMOKES.mkdir(parents=True, exist_ok=True)
    started = time.time()
    record = dict(plan)

    # Exactly one create request, structurally enforced.
    create_once = kling.CreateTaskOnce()
    try:
        task_ref = create_once(config, concept, 0, duration=SMOKE_DURATION)
    except kling.KlingError as exc:
        # No automatic retry. Stop immediately and report the real failure.
        record.update(status="create_failed", error=str(exc), create_requests=create_once.calls)
        _write_record(record)
        raise

    task_id = task_ref["id"]
    record.update(status="created", task_id=task_id, create_requests=create_once.calls)

    task = kling.poll_task(config, task_id, interval=poll_interval, timeout=poll_timeout)
    record.update(status="succeeded", task_status=task.get("status"))

    url = kling.extract_video_url(task)
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime(started))
    dest = SMOKES / f"smoke-{stamp}-task{task_id}.mp4"
    kling.download_video(config, url, dest)

    if not dest.exists() or dest.stat().st_size == 0:
        raise kling.KlingError(f"smoke artifact missing or empty: {dest}")

    assets.write_metadata(dest.with_suffix(".json"), {
        "generator": "kling-live-smoke-test",
        "model": "kling-3.0-omni",
        "endpoint": kling.CREATE_ENDPOINT,
        "concept_id": plan["concept_id"],
        "task_id": task_id,
        "requested_settings": plan["request_body"]["settings"],
        "character_reference": plan["character_reference"],
        "duration": SMOKE_DURATION,
        "paid": True,
        "create_requests": create_once.calls,
        "not_a_production_asset": True,
    })

    # Media validation is reported, not treated as a failure of the smoke test:
    # a single 5s clip is not the 20s production deliverable, and Kling may
    # return a frame rate different from the 30fps production target.
    findings = validate.validate_video(dest)

    record.update(
        status="downloaded",
        artifact=str(dest),
        bytes=dest.stat().st_size,
        validation_findings=findings,
        elapsed_seconds=round(time.time() - started, 1),
    )
    _write_record(record)
    return record


def _write_record(record: dict) -> Path:
    SMOKES.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    path = SMOKES / f"smoke-record-{stamp}.json"
    path.write_text(json.dumps(record, indent=2, default=str))
    return path