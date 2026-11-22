# AI Video Pipeline

[![CI](https://github.com/Anondevnet/ai-video-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/Anondevnet/ai-video-pipeline/actions/workflows/ci.yml)

![Demo](docs/demo.gif)

A restartable pipeline for planning short-form vertical videos, generating clips, assembling a 20-second 1080×1920 render, and exporting a captioned package.

Clip generation has two modes:

- **Mock mode** (tested): ffmpeg `testsrc2` produces clearly labeled placeholder clips. No paid API calls are made.
- **Live mode** (implemented, not live-tested): a Kling 3.0 Omni client that builds the official request, polls the task, and downloads the result. Live calls require credentials and an explicit `--live` / `--confirm-live` opt-in. Those paths have been unit-tested with mocks. They have **not** been executed against the real Kling API.

Scripts and concepts are produced by deterministic, seeded templates, not by an LLM.

## Architecture

```
config/ + trends/  →  planner  →  scripts
                              →  Kling client (live) or ffmpeg mock
                              →  clip assets + sidecar metadata
                              →  ffmpeg render (1080x1920 @ 30fps)
                              →  validate  →  export package
                              ↖ checkpoint state (atomic JSON)
```

| Path | Role |
|---|---|
| `config/` | character spec and content strategy |
| `trends/` | optional trend input JSON (no live credentials required) |
| `src/aiinf/` | pipeline package: planning, scripts, Kling client, render, validation, state |
| `reference/` | optional character reference still used for consistency in live requests |
| `run.py` | CLI |
| `tests/` | unit and integration tests, including live-safety guards |

On every invocation the orchestrator reads `state/pipeline_state.json`, checks that the last completed stage still has artifacts on disk, and resumes from the first incomplete stage. Completed stages are skipped.

## Stack

Python 3 (standard library), ffmpeg, and pytest. Kling authentication uses either a bearer API key or an Access Key / Secret Key JWT built with the standard library. There is no third-party SDK.

## Setup

Install ffmpeg (for example `brew install ffmpeg`) and Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env.example` documents `KLING_ACCESS_KEY` / `KLING_SECRET_KEY` or `KLING_API_KEY`, `KLING_BASE_URL`, `KLING_MOCK`, and `KLING_LIVE_AUTHORIZED`. Leave live authorization at `0` unless you intend to spend money on a real generation.

```bash
python3 -m pytest tests -q
python3 run.py status
python3 run.py plan --lane both
python3 run.py run --mock --lane evergreen
```

Live generation, when you have credentials and accept the cost:

```bash
python3 run.py run --live --lane fresh_trending --concept-limit 1
```

`run --live` refuses existing mock-labeled clips, defaults to one concept, and does not advance a concept past `clips_generated` if generation fails. `python3 run.py live-smoke-test` previews the request. It issues a single paid create only with `--confirm-live`.

## Tests

```bash
python3 -m pytest tests -q
```

75 tests passed in this publication run (Python 3.11, ffmpeg available). Coverage includes character and schema validation, script structure, asset naming, checkpoint state, ffmpeg render/validate fixtures, restart idempotency, mocked Kling request and poll handling, and live-safety guards (mock artifacts cannot be promoted into a live run). ffmpeg is required for the render and validation tests.


## Results

Recorded in [GitHub Actions](https://github.com/Anondevnet/ai-video-pipeline/actions/runs/45046511944) on 22 November 2026, `ubuntu-latest`, Python 3.11, ffmpeg installed, mock mode (`KLING_MOCK=1`, `KLING_LIVE_AUTHORIZED=0`):

| Metric | Value |
|---|---|
| Tests passed | 75 |

## Status and limitations

- Mock pipeline runs, validation, and restart recovery have been exercised locally with ffmpeg placeholders.
- Live Kling calls are untested against the real endpoint. Remaining unknowns are gateway acceptance of the JWT or API key, the exact `outputs` payload shape, and signed URL download behavior.
- No paid Kling request was made in the development of this repository.
- The included character (Zyra Rex) is a fully original fictional persona, not a depiction of a real person.
- Generated clips, renders, and export packages are not committed. They are recreated by a mock or live run.
