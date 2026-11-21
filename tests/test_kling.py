import base64
import io
import json
import urllib.error
import urllib.request
from unittest import mock

import pytest

from aiinf import kling
from aiinf.env import KlingConfig


def cfg(**kw):
    base = dict(api_key=None, access_key="ak_test", secret_key="sk_test",
                base_url="https://api-singapore.klingai.com", mock=False, live_authorized=True)
    base.update(kw)
    return KlingConfig(**base)


class FakeResp:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def concept():
    from aiinf.planner import plan_concepts
    return plan_concepts(lane="evergreen", n_per_lane=1)[0]


def test_payload_structure():
    p = kling.build_request_payload(concept(), 0, duration=5)
    assert set(p) == {"contents", "settings", "options"}
    assert p["contents"][0]["type"] == "prompt"
    assert p["settings"]["duration"] == 5
    assert p["settings"]["aspect_ratio"] == "9:16"
    assert p["settings"]["resolution"] == "1080p"
    assert "model" not in p and "mode" not in p and "reference" not in p


def test_payload_duration_bounds():
    with pytest.raises(ValueError):
        kling.build_request_payload(concept(), 0, duration=2)
    with pytest.raises(ValueError):
        kling.build_request_payload(concept(), 0, duration=20)


def test_auth_jwt_from_access_secret():
    h = kling.auth_header(cfg())
    assert h.startswith("Bearer ")
    token = h.split(" ", 1)[1]
    payload = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    assert payload["iss"] == "ak_test"
    assert payload["exp"] > payload["nbf"]


def test_auth_api_key_passthrough():
    h = kling.auth_header(cfg(access_key=None, secret_key=None, api_key="tok123"))
    assert h == "Bearer tok123"


def test_create_task_success():
    resp = {"code": 0, "message": "ok", "request_id": "r1",
            "data": {"id": "task_123", "status": "submitted", "create_time": 1, "update_time": 1, "external_id": ""}}
    with mock.patch.object(urllib.request, "urlopen", return_value=FakeResp(resp)):
        data = kling.create_task(cfg(), concept(), 0)
    assert data["id"] == "task_123"


def test_create_task_api_error():
    resp = {"code": 1000, "message": "auth failed", "request_id": "r2"}
    with mock.patch.object(urllib.request, "urlopen", return_value=FakeResp(resp)):
        with pytest.raises(kling.KlingError, match="1000"):
            kling.create_task(cfg(), concept(), 0)


def test_create_task_missing_id():
    resp = {"code": 0, "message": "ok", "request_id": "r3", "data": {"status": "submitted"}}
    with mock.patch.object(urllib.request, "urlopen", return_value=FakeResp(resp)):
        with pytest.raises(kling.KlingError, match="missing task id"):
            kling.create_task(cfg(), concept(), 0)


def test_poll_task_success_then_succeeded():
    submitted = {"code": 0, "data": [{"id": "t", "status": "submitted"}]}
    processing = {"code": 0, "data": [{"id": "t", "status": "processing"}]}
    done = {"code": 0, "data": [{"id": "t", "status": "succeeded",
                                "outputs": [{"type": "video", "url": "https://x/v.mp4", "duration": "5"}]}]}
    seq = [FakeResp(submitted), FakeResp(processing), FakeResp(done)]
    with mock.patch.object(urllib.request, "urlopen", side_effect=seq), mock.patch("time.sleep"):
        task = kling.poll_task(cfg(), "t", interval=0)
    assert task["status"] == "succeeded"
    assert kling.extract_video_url(task) == "https://x/v.mp4"


def test_poll_task_failed():
    failed = {"code": 0, "data": [{"id": "t", "status": "failed", "message": "content risk control"}]}
    with mock.patch.object(urllib.request, "urlopen", return_value=FakeResp(failed)):
        with pytest.raises(kling.KlingError, match="content risk control"):
            kling.poll_task(cfg(), "t", interval=0)


def test_poll_task_malformed():
    bad = {"unexpected": True}
    with mock.patch.object(urllib.request, "urlopen", return_value=FakeResp(bad)):
        with pytest.raises(kling.KlingError):
            kling.poll_task(cfg(), "t", interval=0)


def test_extract_video_url_missing():
    with pytest.raises(kling.KlingError, match="no video URL"):
        kling.extract_video_url({"status": "succeeded", "outputs": []})


def test_http_error_handling():
    body = json.dumps({"code": 401, "message": "invalid token", "request_id": "r9"}).encode()
    err = urllib.error.HTTPError("u", 401, "Unauthorized", {}, io.BytesIO(body))
    with mock.patch.object(urllib.request, "urlopen", side_effect=err):
        with pytest.raises(kling.KlingError, match="invalid token"):
            kling.get_task(cfg(), "t")


def test_download_empty_file(tmp_path):
    class Empty:
        def read(self, n=-1):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    with mock.patch.object(urllib.request, "urlopen", return_value=Empty()):
        with pytest.raises(kling.KlingError, match="empty"):
            kling.download_video(cfg(), "https://x/v.mp4", tmp_path / "v.mp4")
