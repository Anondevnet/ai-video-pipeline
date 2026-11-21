# AGENTS.md — AI Influencer Run

Autonomous engineering loop for this project. Follow it literally.

## Loop

INSPECT → PLAN → IMPLEMENT → VERIFY → AUDIT → UPDATE PROJECT_STATUS.md → CONTINUE

## Rules

1. Never assume a previous step succeeded. Inspect before modifying.
2. Never overwrite successful artifacts unnecessarily; never regenerate a valid asset just because a run restarted.
3. Keep generated assets deterministic/recoverable where practical (stable IDs, sidecar metadata).
4. Record important decisions and failures in PROJECT_STATUS.md and logs/.
5. Keep API keys and secrets out of logs and files. Use environment variables.
6. Prefer small, testable components.
7. Every major phase must have a verification step.
8. If blocked by missing credentials/API access, document the blocker instead of fabricating success.
9. The system must be safely restartable after an unexpected shutdown. Resume from the last verified checkpoint; never duplicate generation for finished stages.
10. Kling 3.0 Omni integration is a boundary: request construction, polling, and response handling are implemented and tested with mocks; real calls only happen with explicit credentials and explicit `--live` authorization.
11. No paid API calls without explicit user authorization.

## Architecture

- config/ — canonical character spec, content strategy (versioned source of truth)
- trends/ — trend input JSON (manual or imported; no live credentials required)
- src/aiinf/ — pipeline package
  - env.py — env var + secret handling
  - character.py — character spec loading/validation
  - schemas.py — content concept/script schema validation
  - planner.py — concept planning (fresh + evergreen lanes)
  - scripts.py — hook/script/caption generation (deterministic templates, seeded)
  - kling.py — Kling 3.0 Omni client (live or explicit mock)
  - assets.py — asset naming, sidecar metadata, lookup
  - state.py — pipeline state checkpoints (atomic JSON writes)
  - render.py — ffmpeg-based assembly of clips into 20s vertical renders
  - validate.py — duration/resolution/orientation/fps/audio/integrity checks
  - pipeline.py — orchestrator, idempotent stages
- reference/ — canonical reference material
- frames/ — intermediate visuals
- clips/ — generated clips
- renders/ — final 20s outputs
- exports/ — publishing-ready packages (video + caption + metadata)
- state/pipeline_state.json — checkpoint state
- logs/ — execution logs
- run.py — CLI entry

## Commands

- `python3 -m pytest tests -q` — run tests
- `python3 run.py status` — show pipeline state
- `python3 run.py plan --lane both` — plan concepts (fresh + evergreen)
- `python3 run.py generate --concept <id> --mock` — mock clip generation (no paid calls)
- `python3 run.py render --concept <id>` — assemble render (requires clips)
- `python3 run.py validate` — validate renders
- `python3 run.py run --mock` — full pipeline in explicit mock mode
- `python3 run.py run --live` — full pipeline against real Kling (requires credentials; costs money)

## Restart semantics

On any invocation, pipeline.py first reads state/pipeline_state.json, verifies the last successful stage's artifacts on disk, and continues from the first incomplete stage. Completed stages are skipped. A crash mid-stage leaves the state pointer at the last completed stage.
