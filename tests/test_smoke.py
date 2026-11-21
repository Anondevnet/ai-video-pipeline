"""Live smoke-test behavior tests.

Every HTTP interaction is mocked. No Kling endpoint is contacted, and no real
paid request can be issued by these tests.
"""
import json
import urllib.error
import urllib.request
from unittest import mock

import pytest

from aiinf import kling, smoke
from aiinf.env import KlingConfig

LIVE_ENV = {
    "KLING_API_KEY": "secret-key-value",
    "KLING_BASE_URL": "https://api-singapore.klingai.com",
    "KLING_MOCK": "0",
    "KLING_LIVE_AUTHORIZED": "1",
}


class FakeResp:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _cfg(**kw):
    base = dict(api_key="secret-key-value", access_key=None, secret_key=None,
                base_url="https://api-singapore.klingai.com", mock=False, live_authorized=True)
    base.update(kw)
    return KlingConfig(**base)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Any un-mocked urlopen call fails the test loudly."""

    def blocked(*a, **kw):
        raise AssertionError("unexpected network call")
    monkeypatch.setattr(urllib.request, "urlopen", blocked)


def _stub(monkeypatch, responses):
    """Mock urlopen with a scripted response sequence; records calls."""
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResp(item)
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return calls


CREATED = {"code": 0, "message": "ok", "request_id": "r1",
           "data": {"id": "task_abc", "status": "submitted"}}
DONE = {"code": 0, "message": "ok", "request_id": "r1",
        "data": [{"id": "task_abc", "status": "succeeded",
                  "outputs": [{"type": "video", "url": "https://cdn/v.mp4", "duration": "5"}]}]}


# --- dry run ---------------------------------------------------------------

def test_dry_run_makes_no_request_and_redacts_key():
    report = smoke.preview(env=LIVE_ENV)
    assert report["max_create_requests"] == 1
    assert report["config"]["api_key_value"] == "<redacted>"
    assert "secret-key-value" not in json.dumps(report)
    assert report["request_body"]["settings"]["duration"] == 5
    assert report["request_body"]["settings"]["aspect_ratio"] == "9:16"
    assert report["config"]["auth_mode"] == "api_key"


def test_dry_run_without_confirm_makes_no_request():
    report = smoke.run_smoke_test(confirm=False, env=LIVE_ENV)
    assert report["mode"].startswith("dry-run")
    assert "task_id" not in report


def test_dry_run_without_credentials_still_previews(monkeypatch):
    """A preview must still render without credentials, flagging their absence."""
    env = dict(LIVE_ENV, KLING_API_KEY="")
    report = smoke.run_smoke_test(confirm=False, env=env)
    assert report["mode"].startswith("dry-run")
    assert "NOT present" in report["note"]
    assert report["config"]["auth_mode"] == "none"
    assert "task_id" not in report


def test_refuses_when_not_authorized():
    env = dict(LIVE_ENV, KLING_LIVE_AUTHORIZED="0")
    with pytest.raises(kling.KlingError, match="live not authorized"):
        smoke.run_smoke_test(confirm=True, env=env)


def test_refuses_when_mock_mode_on():
    env = dict(LIVE_ENV, KLING_MOCK="1")
    with pytest.raises(kling.KlingError, match="KLING_MOCK=1"):
        smoke.run_smoke_test(confirm=True, env=env)


def test_refuses_without_credentials():
    env = dict(LIVE_ENV, KLING_API_KEY="")
    with pytest.raises(kling.KlingError, match="no Kling credentials"):
        smoke.run_smoke_test(confirm=True, env=env)


# --- happy path ------------------------------------------------------------

def test_exactly_one_create_request_and_download(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "SMOKES", tmp_path / "smokes")
    calls = _stub(monkeypatch, [CREATED, DONE])

    # download: return bytes
    def fake_dl(config, url, dest, timeout=300):
        from pathlib import Path
        p = Path(dest)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"fake-video-bytes")
        return p
    monkeypatch.setattr(kling, "download_video", fake_dl)

    report = smoke.run_smoke_test(confirm=True, env=LIVE_ENV, poll_interval=0)

    assert report["create_requests"] == 1
    posts = [c for c in calls if c.get_method() == "POST"]
    gets = [c for c in calls if c.get_method() == "GET"]
    assert len(posts) == 1, f"expected exactly one POST, got {len(posts)}"
    assert len(gets) == 1, "polling must not create another task"
    assert posts[0].full_url.endswith("/omni-video/kling-3.0-omni")
    assert report["task_id"] == "task_abc"
    assert report["status"] == "downloaded"
    assert report["bytes"] > 0


def test_polling_uses_get_and_repeats_only_the_same_task(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "SMOKES", tmp_path / "smokes")
    processing = {"code": 0, "data": [{"id": "task_abc", "status": "processing"}]}
    calls = _stub(monkeypatch, [CREATED, processing, processing, DONE])
    monkeypatch.setattr(kling, "download_video",
                        lambda c, u, d, timeout=300: (open(d, "wb").write(b"x"), d)[1])

    report = smoke.run_smoke_test(confirm=True, env=LIVE_ENV, poll_interval=0)

    posts = [c for c in calls if c.get_method() == "POST"]
    assert len(posts) == 1
    gets = [c.full_url for c in calls if c.get_method() == "GET"]
    assert len(gets) == 3
    assert all("task_ids=task_abc" in g for g in gets)
    assert report["create_requests"] == 1


def test_create_task_once_guard_blocks_second_create():
    guard = kling.CreateTaskOnce()
    with mock.patch.object(kling, "create_task", return_value={"id": "t1"}):
        guard(_cfg(), None, 0)
        with pytest.raises(kling.KlingError, match="exactly one"):
            guard(_cfg(), None, 0)
    assert guard.calls == 1


# --- failure paths ---------------------------------------------------------

def test_create_failure_stops_without_retry(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "SMOKES", tmp_path / "smokes")
    err = {"code": 1002, "message": "insufficient balance", "request_id": "rX"}
    calls = _stub(monkeypatch, [err])
    with pytest.raises(kling.KlingError, match="1002"):
        smoke.run_smoke_test(confirm=True, env=LIVE_ENV, poll_interval=0)
    posts = [c for c in calls if c.get_method() == "POST"]
    assert len(posts) == 1, "must not retry creation after failure"


def test_malformed_create_response(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "SMOKES", tmp_path / "smokes")
    _stub(monkeypatch, [{"unexpected": "shape"}])
    with pytest.raises(kling.KlingError, match="unexpected response shape"):
        smoke.run_smoke_test(confirm=True, env=LIVE_ENV, poll_interval=0)


def test_missing_task_id(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "SMOKES", tmp_path / "smokes")
    _stub(monkeypatch, [{"code": 0, "data": {"status": "submitted"}}])
    with pytest.raises(kling.KlingError, match="missing task id"):
        smoke.run_smoke_test(confirm=True, env=LIVE_ENV, poll_interval=0)


def test_failed_task_reports_real_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "SMOKES", tmp_path / "smokes")
    failed = {"code": 0, "data": [{"id": "task_abc", "status": "failed",
                                   "message": "content risk control triggered"}]}
    calls = _stub(monkeypatch, [CREATED, failed])
    with pytest.raises(kling.KlingError, match="content risk control"):
        smoke.run_smoke_test(confirm=True, env=LIVE_ENV, poll_interval=0)
    assert len([c for c in calls if c.get_method() == "POST"]) == 1


def test_missing_video_url(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "SMOKES", tmp_path / "smokes")
    done_no_url = {"code": 0, "data": [{"id": "task_abc", "status": "succeeded", "outputs": []}]}
    _stub(monkeypatch, [CREATED, done_no_url])
    with pytest.raises(kling.KlingError, match="no video URL"):
        smoke.run_smoke_test(confirm=True, env=LIVE_ENV, poll_interval=0)


def test_http_error_on_create(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "SMOKES", tmp_path / "smokes")
    import io
    body = json.dumps({"code": 401, "message": "invalid api key", "request_id": "rE"}).encode()
    http_err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(body))
    _stub(monkeypatch, [http_err])
    with pytest.raises(kling.KlingError, match="invalid api key"):
        smoke.run_smoke_test(confirm=True, env=LIVE_ENV, poll_interval=0)


def test_empty_download_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "SMOKES", tmp_path / "smokes")
    _stub(monkeypatch, [CREATED, DONE])

    def empty_download(config, url, dest, timeout=300):
        from pathlib import Path
        p = Path(dest)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
        return p
    monkeypatch.setattr(kling, "download_video", empty_download)
    with pytest.raises(kling.KlingError, match="missing or empty"):
        smoke.run_smoke_test(confirm=True, env=LIVE_ENV, poll_interval=0)


def test_secret_never_appears_in_error_or_record(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "SMOKES", tmp_path / "smokes")
    _stub(monkeypatch, [{"code": 1002, "message": "denied"}])
    with pytest.raises(kling.KlingError) as ei:
        smoke.run_smoke_test(confirm=True, env=LIVE_ENV, poll_interval=0)
    assert "secret-key-value" not in str(ei.value)
    records = list((tmp_path / "smokes").glob("smoke-record-*.json"))
    assert records, "a failure record should be written"
    body = "".join(r.read_text() for r in records)
    assert "secret-key-value" not in body
    assert "<redacted>" in body


# --- production isolation --------------------------------------------------

def test_smoke_does_not_touch_clips_renders_or_state(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "SMOKES", tmp_path / "smokes")
    _stub(monkeypatch, [CREATED, DONE])
    monkeypatch.setattr(kling, "download_video",
                        lambda c, u, d, timeout=300: (open(d, "wb").write(b"x"), d)[1])

    def forbidden_state(*a, **kw):
        raise AssertionError("smoke test must not write production pipeline state")
    monkeypatch.setattr("aiinf.state.save_state", forbidden_state)

    smoke.run_smoke_test(confirm=True, env=LIVE_ENV, poll_interval=0)


def test_production_plan_unchanged():
    """The smoke test must not alter production clip plan/targets."""
    from aiinf.character import load_strategy
    s = load_strategy()
    assert s["clip_plan"]["clips"] == 4
    assert s["clip_plan"]["total_target_seconds"] == 20
    assert s["target_resolution"] == [1080, 1920]
    assert s["target_duration_seconds"] == 20
    # smoke uses exactly one clip, matching the production per-clip duration
    assert smoke.SMOKE_DURATION == 5
    assert smoke.SMOKE_ASPECT_RATIO == "9:16"
    assert smoke.SMOKE_RESOLUTION == "1080p"