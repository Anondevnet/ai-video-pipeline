import os
from datetime import datetime, timezone
import json
import shutil
from pathlib import Path

from . import assets, kling, reference, render, scripts, validate
from .character import load_character, load_strategy
from .env import load_kling_config
from .paths import CLIPS, EXPORTS, RENDERS, STATE_FILE
from .planner import plan_concepts
from .schemas import Concept
from .state import advance, load_state, save_state, stage_index, STAGES

STAGE_ORDER = STAGES

MOCK_GENERATOR = "kling-mock-ffmpeg-testsrc2"


def _reference_kwargs(character: dict) -> tuple[dict, dict]:
    """Resolve the configured character reference into payload kwargs.

    Returns (kwargs_for_build_request_payload, status_for_reporting). If the
    configured image is absent the request stays prompt-only; nothing is
    fabricated and no external upload is performed.
    """
    ref = reference.resolve(character)
    if not ref.get("attached"):
        return {}, {"attached": False, "reason": ref.get("reason")}
    role = ref.get("role", "refer_image")
    key = "first_frame_url" if role == "first_frame" else "refer_image_url"
    return {key: reference.to_data_uri(ref["path"])}, {"attached": True, "role": role,
                                                        "dimensions": f"{ref['width']}x{ref['height']}"}


def _concept_path(concept_id: str) -> Path:
    d = Path(__file__).resolve().parents[2] / "exports" / concept_id
    return d


class MockArtifactConflict(RuntimeError):
    """Raised when live mode encounters a clip previously produced by the mock generator."""


def _clip_origin(clip: Path) -> str | None:
    """Return the recorded generator for an existing clip, or None if unknown/absent."""
    meta = Path(clip).with_suffix(".json")
    if not meta.exists():
        return None
    try:
        return json.loads(meta.read_text()).get("generator")
    except (json.JSONDecodeError, OSError):
        return None


def _has_artifacts(concept_id: str) -> bool:
    slug = assets.concept_slug(concept_id)
    return bool(list(CLIPS.glob(f"{slug}-clip*")) or list(RENDERS.glob(f"{slug}-final*")))


def export_package(concept: Concept, render_file: Path, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(render_file, out_dir / render_file.name)
    meta = {
        "concept": concept.to_dict(),
        "caption": scripts.generate_caption(concept),
        "script": scripts.generate_script(concept),
        "hashtags": ["#hiphop", "#shorts", "#zyrarex"],
        "video": render_file.name,
        "publishing_ready": True,
    }
    (out_dir / "publish.json").write_text(json.dumps(meta, indent=2))
    return meta


def run_pipeline(lane: str = "both", mock: bool = False, live: bool = False, concept_limit: int | None = None) -> dict:
    state = load_state()
    character = load_character()
    strategy = load_strategy()
    cfg = load_kling_config()
    if live:
        if not cfg.can_call_live:
            raise RuntimeError("live requested but credentials/authorization missing; document blocker, do not fabricate")
        cfg.mock = False
    elif mock:
        cfg.mock = True

    concepts = plan_concepts(lane=lane)

    if live:
        # Safety: the first paid test must never reuse mock artifacts or completed generation.
        def _usable(c):
            stage = state["concepts"].get(c.id, {}).get("last_stage", "init")
            return not _has_artifacts(c.id) and stage_index(stage) < stage_index("clips_generated")
        usable = [c for c in concepts if _usable(c)]
        if not usable:
            raise RuntimeError(
                "no un-started concept without existing artifacts in lane "
                f"'{lane}'; refusing live run to protect mock fixtures"
            )
        if concept_limit is None:
            concept_limit = 1
        if concept_limit < 1:
            raise ValueError("--concept-limit must be >= 1")
        concepts = usable[:concept_limit]
    elif concept_limit:
        concepts = concepts[:concept_limit]

    results = []
    ref_kwargs, ref_status = _reference_kwargs(character)
    for c in concepts:
        rec = state["concepts"].get(c.id, {})
        cur = rec.get("last_stage", "init")

        # stage: planned
        if stage_index(cur) < stage_index("planned"):
            advance(state, c.id, "planned", {"concept": str(_concept_path(c.id) / "concept.json")})
            p = _concept_path(c.id); p.mkdir(parents=True, exist_ok=True)
            (p / "concept.json").write_text(json.dumps(c.to_dict(), indent=2))
            cur = "planned"
            save_state(state)

        # stage: scripted
        if stage_index(cur) < stage_index("scripted"):
            script = scripts.generate_script(c, character)
            p = _concept_path(c.id); (p / "script.json").write_text(json.dumps(script, indent=2))
            advance(state, c.id, "scripted", {"script": str(p / "script.json")})
            cur = "scripted"
            save_state(state)

        # stage: clips_generated
        if stage_index(cur) < stage_index("clips_generated"):
            clip_meta = []
            try:
                for i in range(strategy["clip_plan"]["clips"]):
                    dest = assets.clip_path(CLIPS, c.id, i)
                    if dest.exists() and dest.stat().st_size > 0:
                        origin = _clip_origin(dest)
                        if live and origin == MOCK_GENERATOR:
                            raise MockArtifactConflict(
                                f"{dest.name} was produced by {MOCK_GENERATOR}; live mode will not "
                                f"reuse mock artifacts. Choose a concept with no existing clips."
                            )
                        clip_meta.append(str(dest))
                        continue
                    if mock:
                        kling.generate_clip_mock(c, i, dest, duration=strategy["clip_plan"]["min_clip_seconds"] + 1)
                    elif live:
                        job = kling.create_task(cfg, c, i, **ref_kwargs)
                        task = kling.poll_task(cfg, job["id"])
                        url = kling.extract_video_url(task)
                        kling.download_video(cfg, url, dest)
                    else:
                        raise RuntimeError(f"no clips for {c.id} and neither --mock nor --live authorized; stopping at clips_generated")
                    clip_meta.append(str(dest))
            except Exception as exc:
                # generation failed: do NOT advance the stage, record the real error
                rec_err = state["concepts"].setdefault(c.id, {"last_stage": cur, "artifacts": {}, "errors": []})
                rec_err.setdefault("errors", []).append(f"{type(exc).__name__}: {exc}")
                save_state(state)
                results.append({"concept": c.id, "status": "generation_failed", "stage": cur,
                                "error": f"{type(exc).__name__}: {exc}"})
                continue
            advance(state, c.id, "clips_generated", {"clips": clip_meta, "character_reference": ref_status})
            cur = "clips_generated"
            save_state(state)

        # stage: rendered
        out_render = assets.render_path(RENDERS, c.id)
        if stage_index(cur) < stage_index("rendered"):
            if not out_render.exists():
                render.render_from_clips(c.id)
            advance(state, c.id, "rendered", {"render": str(out_render)})
            cur = "rendered"
            save_state(state)

        # stage: validated
        if stage_index(cur) < stage_index("validated"):
            errs = validate.validate_render(out_render, target_duration=20)
            if errs:
                state["concepts"][c.id].setdefault("errors", []).extend(errs)
                save_state(state)
                results.append({"concept": c.id, "status": "validation_failed", "errors": errs})
                continue
            advance(state, c.id, "validated", {"validated": True, "render": str(out_render)})
            cur = "validated"
            save_state(state)

        # stage: exported
        if stage_index(cur) < stage_index("exported"):
            export_package(c, out_render, _concept_path(c.id))
            advance(state, c.id, "exported", {"export": str(_concept_path(c.id))})
            save_state(state)

        results.append({"concept": c.id, "status": "ok", "render": str(out_render)})

    return {"results": results, "last_stage": state["last_stage"]}
