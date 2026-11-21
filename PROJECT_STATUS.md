# PROJECT_STATUS.md — AI Influencer Run

## Current Phase
COMPLETED — Mock pipeline run, validation, restart recovery verified

## Completed Phases
- [x] Project scaffolding (dirs, AGENTS.md)
- [x] Character specification (Kayo Reign — original fictional hip-hop persona)
- [x] Content strategy (20s vertical, hip-hop niche, fresh+evergreen lanes)
- [x] Trend input (trends/trends.json)
- [x] Environment config (.env.example, no real secrets)
- [x] Core pipeline modules (src/aiinf/*)
  - env.py — Kling config, secret handling
  - character.py — spec loading/validation
  - schemas.py — concept schema, validation
  - planner.py — deterministic concept planning (seeded RNG)
  - scripts.py — hook/script/caption generation
  - kling.py — Kling 3.0 Omni client (live + explicit mock via ffmpeg testsrc2)
  - assets.py — naming, sidecar metadata
  - state.py — atomic checkpoint state
  - render.py — ffmpeg concat+scale to 1080x1920@30fps
  - validate.py — duration/resolution/orientation/fps/audio/integrity
  - pipeline.py — idempotent orchestrator with per-concept checkpoints
- [x] CLI (run.py) — status, plan, run (--mock/--live)
- [x] Tests (18 passing)
  - test_character, test_schemas, test_scripts, test_assets, test_state, test_validate, test_restart
- [x] Mock pipeline run (`python3 run.py run --mock --lane evergreen`)
- [x] Restart recovery verification (second run skipped all stages, mtimes unchanged)

## Current Task
None — at stable checkpoint

## Blockers
- **Kling 3.0 Omni credentials unavailable** — real generation blocked
  - KLING_API_KEY / KLING_ACCESS_KEY+SECRET_KEY not set
  - KLING_LIVE_AUTHORIZED=0 (explicit opt-in required)
  - Integration boundary implemented: request construction, polling, response handling, download — all untested against live endpoint
  - Mock mode uses ffmpeg testsrc2, clearly labeled in metadata as `generator: "kling-mock-ffmpeg-testsrc2"`

## Configuration Decisions
- Character: Kayo Reign (@kayoreign) — fully original fictional
- Niche: hip-hop
- Caption language: English
- Target: 20s, 1080x1920, 30fps, vertical
- Lanes: fresh_trending + evergreen (planner supports both)
- Model: kling-3.0-omni
- Clip plan: 4 clips × 5s = 20s
- All secrets via env vars; .env.example provided
- Deterministic generation via seeded RNG (concept-id based)
- Idempotent stages: artifacts verified before regeneration
- Checkpoint state: state/pipeline_state.json (atomic writes)

## Files Created
```
AGENTS.md
PROJECT_STATUS.md
.env.example
config/character.json
config/strategy.json
trends/trends.json
src/aiinf/__init__.py
src/aiinf/paths.py
src/aiinf/env.py
src/aiinf/character.py
src/aiinf/schemas.py
src/aiinf/planner.py
src/aiinf/scripts.py
src/aiinf/assets.py
src/aiinf/kling.py
src/aiinf/state.py
src/aiinf/render.py
src/aiinf/validate.py
src/aiinf/pipeline.py
run.py
pytest.ini
tests/conftest.py
tests/test_character.py
tests/test_schemas.py
tests/test_scripts.py
tests/test_assets.py
tests/test_state.py
tests/test_validate.py
tests/test_restart.py
```
Artifacts generated during mock run:
```
clips/evergreen-00{1,2}-clip{0..3}.mp4 (+ .json sidecars)
renders/evergreen-00{1,2}-final.mp4 (+ .json sidecars)
exports/evergreen-00{1,2}/publish.json (video + caption + metadata)
state/pipeline_state.json
```

## Tests Run / Results
```
pytest tests -q
18 passed in ~16s
```
- Unit tests: character loading, schema validation, script structures, asset naming, state roundtrip
- Integration: validate_video/render with real ffmpeg fixtures
- End-to-end: full mock pipeline + restart idempotency (slow test)

## Verification Results
- Mock renders: 1080x1920, 20.00s, h264 + aac, vertical ✓
- Validation passes for mock outputs ✓
- Restart: second `run_pipeline(mock=True)` skipped all stages, file mtimes unchanged ✓
- No secrets committed (grep finds none) ✓
- No paid API calls made (KLING_MOCK=1, no KLING_LIVE_AUTHORIZED) ✓
- Kling integration marked unconfigured in state and logs ✓

## Next Action
To proceed with real generation:
1. Obtain Kling 3.0 Omni credentials (API key or access/secret key)
2. Set env: `KLING_API_KEY=...` (or KLING_ACCESS_KEY+KLING_SECRET_KEY)
3. Set `KLING_LIVE_AUTHORIZED=1` (explicit opt-in)
4. Run: `python3 run.py run --live --lane both` (will incur costs)

Or plan fresh concepts: `python3 run.py plan --lane fresh_trending`

## Last Successful Checkpoint
- State: `state/pipeline_state.json` (last_stage=exported, both evergreen concepts complete)
- Time: 2026-10-06T19:41:39.720351+00:00
- Artifacts verified on disk

## Timestamp
2026-10-06T19:42:00+00:00
---

## Kling Live-Integration Audit (2026-10-06, pre-paid)

Source audited: official docs at kling.ai/document-api/api/video/3-0-omni/video-omni (fetched via .md variant) + 2026 community/auth guides.

Verified against docs / code changes made:
- Base URL: `https://api-singapore.klingai.com` (env.py default updated from outdated `api.klingai.com`)
- Auth: `Authorization: Bearer <token>`; token = JWT (HS256, iss=AccessKey, exp=now+1800, nbf=now-5) signed with SecretKey — now implemented in `kling.make_jwt` via stdlib only. Raw `X-Access-Key`/`X-Secret-Key` headers were REMOVED (invalid). `KLING_API_KEY` passthrough as Bearer also supported.
- Create endpoint: `POST /omni-video/kling-3.0-omni` (was wrong: `/v1/videos/omni-video`)
- Poll endpoint: `GET /tasks?task_ids=<id>` (was wrong: `POST {ENDPOINT}/{id}`); response `data` is a LIST, first element used
- Statuses: `submitted`, `processing`, `succeeded`, `failed` (old parser expected `succeed`/`completed`)
- Payload: `{contents:[{type:"prompt",text}], settings:{resolution,duration,aspect_ratio,audio,multi_shot}, options:{...}}` — old `model`/`mode`/`reference`/`aspect_ratio`(top-level) fields removed; model is in the path
- Duration: int 3–15 (old stub sent raw values; now validated, 3–15)
- aspect_ratio `9:16` now under `settings`; resolution `1080p`
- Create response: `{code,message,request_id,data:{id,status,...}}` — requires code==0 and data.id, else KlingError
- Video URL: `data[0].outputs[*]` where `type=="video"` → `.url` (old parser wrongly read top-level `video_url`)
- Errors: `{code!=0,message,request_id}` surfaced; HTTPError bodies parsed; timeouts; malformed JSON; missing id/url; empty download — all raise KlingError, never fake success
- Download: plain GET on signed output URL (no auth header), empty-file guard

Still UNVERIFIED (requires real credentials + explicit authorization):
- JWT acceptance against the live gateway
- Exact response shape of `data[0].outputs` in practice
- Download URL accessibility without extra headers
- Any model-specific behavior of `kling-3.0-omni` path

Tests: 31 passed (18 pre-existing + 13 new in tests/test_kling.py covering payload, auth JWT, create success/error/missing-id, polling success/failed/malformed, missing video URL, HTTP error, empty download). No live calls made.

`python3 run.py status` and `python3 run.py plan --lane fresh_trending` re-verified OK.
`run --live` NOT executed. Project remains mock-only.

---

## Live-Safety Hardening + Model Identifier Re-verification (2026-10-06)

### Reported stale-call bug: NOT PRESENT
The reported `create_job`/`poll_job`/`download` leftovers do not exist in this repo.
Verified by grep across the whole project: 0 matches for `create_job`, `poll_job`, `kling.download(`.
`src/aiinf/pipeline.py:87-91` already contained exactly one coherent live branch:
```
job = kling.create_task(cfg, c, i)
task = kling.poll_task(cfg, job["id"])
url = kling.extract_video_url(task)
kling.download_video(cfg, url, dest)
```
No change was required; nothing was removed because nothing stale was found.

### Model identifier — official-doc re-verification
Official sources re-fetched (kling.ai official documentation only):
- `/api/video/3-0-omni/video-omni.md` → Path: `/omni-video/kling-3.0-omni`
- `/api/get-started/authentication.md` → domain `https://api-singapore.klingai.com`, and the explicit
  rule: "The model version information located in the path is the new version, while the value set as
  the `model_name` parameter is the legacy version."
- `/guides/capability-map/video.md` (updated 2026-05-19) → "Kling 3.0 Omni" 3~15s, 720P/1080P/4K
- `/updates/api.md` (changelog) → `kling-v3-omni` appears only as a legacy `model_name` value /
  model-range label in older entries (e.g. 04/23/2026 4K note, 05/07/2026 first/last-frame note)
  which reference the legacy API design (`mode` parameter, `model_name` parameter).

Conclusion: for the CURRENT (new) API the identifier is the path segment `kling-3.0-omni`.
`kling-v3-omni` belongs to the LEGACY API design that uses a `model_name` body parameter and a
`mode` parameter — which this project does not use. The implementation therefore keeps
`kling-3.0-omni` in the path and sends NO model/mode body fields, which matches the current
official request schema exactly.

### Other contract points confirmed from official docs
- Auth: new API supports API-Key-only (`Authorization: Bearer <API Key from console>`); AK/SK JWT
  remains supported. Code supports both (`KLING_API_KEY` passthrough; AK/SK → stdlib HS256 JWT).
- duration: int 3–15 (validated); resolution: 720p|1080p|4k; aspect_ratio: 16:9|9:16|1:1 (required
  when no first frame / reference video); audio: native|original|off; multi_shot: bool (default true)
- Reference/character consistency: via `contents[]` entries of type `first_frame`, `last_frame`,
  `refer_image`, `feature_video`, `base_video`, `element` (element_id from Element API), referenced
  in the prompt as `@image_1` / `@element_1` etc. Multi-shot prompt format "shot n, m, words;".
- Create response: `{code,message,request_id,data:{id,status,create_time,update_time,external_id}}`
- Poll: `GET /tasks?task_ids=<id>` (batch comma-separated), `data` is an ARRAY
- Statuses: submitted | processing | succeeded | failed
- Output URL: `data[0].outputs[]` where `type=="video"` → `.url` (hotlink-protected, 30-day expiry)
- Errors: `{code!=0, message, request_id}`; code must be 0 to proceed

### Code changes made this round (safety only; no API contract change)
- `src/aiinf/pipeline.py`:
  - `MOCK_GENERATOR` constant + `_clip_origin()` + `MockArtifactConflict`
  - live mode now REFUSES any existing clip whose metadata generator is `kling-mock-ffmpeg-testsrc2`
  - generation failures (any exception during the clip loop) are caught, the real error is recorded
    in state `errors[]`, result status is `generation_failed`, and the concept is NOT advanced to
    `clips_generated` or any later stage
  - live mode selects ONLY concepts that have no existing artifacts and are below `clips_generated`
    in state; if none qualify it refuses the run; live mode defaults to exactly ONE concept
- `run.py`: added `--concept-limit N` (no force/overwrite flag was added)

### Tests
38 passed (was 31). New in `tests/test_live_safety.py`:
- live refuses mock-generated clips (network path asserted unreachable)
- live failure does not advance checkpoint past `clips_generated`
- live refuses when every candidate already has artifacts
- live defaults to exactly one concept
- live rejects `--concept-limit 0`
- `--concept-limit` truncates selection
- mock clips are always labeled non-paid

### No live request occurred
No Kling endpoint was contacted at any point. `python3 run.py run --live` was NOT executed.
Existing mock artifacts preserved: 16 files in clips/, 4 files in renders/, state still shows
evergreen-001=exported, evergreen-002=exported.

### Readiness
The pipeline path has been inspected end-to-end and contains a single coherent live implementation
with no stale call sites. Remaining unverified items are exactly those that require one authorized
paid call: JWT/API-key acceptance by the gateway, the real `outputs` payload shape, and signed-URL
download behavior. Project is ready for ONE controlled live test with `--lane fresh_trending
--concept-limit 1`, but that authorization has NOT been given and no call has been made.
