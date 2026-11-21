import base64
import hashlib
import hmac
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .env import KlingConfig
from . import assets

CREATE_ENDPOINT = "/omni-video/kling-3.0-omni"
QUERY_ENDPOINT = "/tasks"

ALLOWED_DURATIONS = list(range(3, 16))
ALLOWED_ASPECT_RATIOS = ("16:9", "9:16", "1:1")
ALLOWED_RESOLUTIONS = ("720p", "1080p", "4k")
ALLOWED_AUDIO = ("native", "original", "off")
TERMINAL_OK = ("succeeded",)
TERMINAL_FAIL = ("failed",)


class KlingError(RuntimeError):
    pass


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def make_jwt(access_key: str, secret_key: str, now: float | None = None) -> str:
    now = int(time.time()) if now is None else int(now)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"iss": access_key, "exp": now + 1800, "nbf": now - 5}
    signing = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
    sig = hmac.new(secret_key.encode(), signing.encode(), hashlib.sha256).digest()
    return f"{signing}.{_b64url(sig)}"


def auth_header(config: KlingConfig) -> str:
    if config.access_key and config.secret_key:
        return f"Bearer {make_jwt(config.access_key, config.secret_key)}"
    if config.api_key:
        return f"Bearer {config.api_key}"
    raise KlingError("no credentials configured")


def _check_image_ref(value: str, label: str) -> str:
    """Kling accepts a URL or a base64 data URI for image contents."""
    if value.startswith("data:image/") or value.startswith("https://") or value.startswith("http://"):
        return value
    raise ValueError(f"{label} must be an https URL or a base64 data URI")


def build_request_payload(concept, clip_index: int, duration: int = 5,
                          resolution: str = "1080p", aspect_ratio: str = "9:16",
                          audio: str = "off", multi_shot: bool = False,
                          first_frame_url: str | None = None,
                          refer_image_url: str | None = None) -> dict:
    if duration not in ALLOWED_DURATIONS:
        raise ValueError(f"duration must be 3-15s, got {duration}")
    if aspect_ratio not in ALLOWED_ASPECT_RATIOS:
        raise ValueError(f"bad aspect_ratio {aspect_ratio}")
    if resolution not in ALLOWED_RESOLUTIONS:
        raise ValueError(f"bad resolution {resolution}")
    if audio not in ALLOWED_AUDIO:
        raise ValueError(f"bad audio {audio}")
    prompt = f"{concept.visual_direction}. {concept.voiceover}"[:3072]
    contents = [{"type": "prompt", "text": prompt}]
    if first_frame_url:
        contents.append({"type": "first_frame",
                         "url": _check_image_ref(first_frame_url, "first_frame_url"),
                         "id": "image_1"})
    if refer_image_url:
        contents.append({"type": "refer_image",
                         "url": _check_image_ref(refer_image_url, "refer_image_url"),
                         "id": "image_2"})
    return {
        "contents": contents,
        "settings": {
            "resolution": resolution,
            "duration": duration,
            "audio": audio,
            "multi_shot": multi_shot,
            **({"aspect_ratio": aspect_ratio} if not first_frame_url else {}),
        },
        "options": {"watermark_info": {"enabled": False}},
    }


def _request(config: KlingConfig, method: str, path: str, body: dict | None = None,
             timeout: int = 60) -> dict:
    url = config.base_url.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": auth_header(config), "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read())
            raise KlingError(f"HTTP {e.code}: {err.get('message', err)} (request_id={err.get('request_id')})") from e
        except (ValueError, AttributeError):
            raise KlingError(f"HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise KlingError(f"network error: {e.reason}") from e
    try:
        return json.loads(raw)
    except ValueError:
        raise KlingError(f"malformed JSON response from {path}")


class CreateTaskOnce:
    """Guard that permits exactly one create-task POST for its lifetime.

    Used by the live smoke test so a second create request can never be issued,
    even if calling code changes or a retry is attempted. This wraps the existing
    ``create_task`` (same client, same endpoint) rather than adding a second client.
    """

    def __init__(self):
        self.calls = 0
        self.task = None

    def __call__(self, config: KlingConfig, concept, clip_index: int, duration: int = 5, **kw) -> dict:
        if self.calls >= 1:
            raise KlingError("refusing second create-task request (smoke test allows exactly one)")
        self.calls += 1
        self.task = create_task(config, concept, clip_index, duration, **kw)
        return self.task


def _unwrap(resp: dict) -> dict:
    if not isinstance(resp, dict) or "code" not in resp:
        raise KlingError(f"unexpected response shape: {str(resp)[:200]}")
    if resp["code"] != 0:
        raise KlingError(f"API error code={resp['code']} message={resp.get('message')} request_id={resp.get('request_id')}")
    return resp.get("data")


def create_task(config: KlingConfig, concept, clip_index: int, duration: int = 5, **kw) -> dict:
    if not config.can_call_live:
        raise KlingError("live generation not authorized or not configured")
    payload = build_request_payload(concept, clip_index, duration, **kw)
    data = _unwrap(_request(config, "POST", CREATE_ENDPOINT, payload))
    if not isinstance(data, dict) or not data.get("id"):
        raise KlingError(f"create response missing task id: {data}")
    return data


def get_task(config: KlingConfig, task_id: str) -> dict:
    if not config.can_call_live:
        raise KlingError("live polling not authorized")
    qs = urllib.parse.urlencode({"task_ids": task_id})
    data = _unwrap(_request(config, "GET", f"{QUERY_ENDPOINT}?{qs}"))
    if not isinstance(data, list) or not data:
        raise KlingError(f"task query returned no task for id={task_id}")
    return data[0]


def poll_task(config: KlingConfig, task_id: str, interval: float = 10.0, timeout: float = 900.0) -> dict:
    deadline = time.time() + timeout
    while True:
        task = get_task(config, task_id)
        status = task.get("status")
        if status in TERMINAL_OK:
            return task
        if status in TERMINAL_FAIL:
            raise KlingError(f"task {task_id} failed: {task.get('message', 'no message')}")
        if status not in ("submitted", "processing"):
            raise KlingError(f"task {task_id} unknown status: {status}")
        if time.time() >= deadline:
            raise KlingError(f"task {task_id} polling timeout after {timeout}s (last status={status})")
        time.sleep(interval)


def extract_video_url(task: dict) -> str:
    for out in task.get("outputs") or []:
        if out.get("type") == "video" and out.get("url"):
            return out["url"]
    raise KlingError(f"no video URL in task outputs: {json.dumps(task)[:300]}")


def download_video(config: KlingConfig, url: str, dest: Path, timeout: int = 300) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": "aiinf/1.0"})
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
    except urllib.error.HTTPError as e:
        raise KlingError(f"download failed HTTP {e.code}: {e.reason}") from e
    except urllib.error.URLError as e:
        raise KlingError(f"download network error: {e.reason}") from e
    if dest.stat().st_size == 0:
        dest.unlink()
        raise KlingError("downloaded file is empty")
    return dest


def generate_clip_mock(concept, clip_index: int, dest: Path, duration: int = 5, size: str = "720x1280") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={duration}",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    assets.write_metadata(dest.with_suffix(".json"), {
        "generator": "kling-mock-ffmpeg-testsrc2",
        "model": "mock",
        "concept_id": concept.id,
        "clip_index": clip_index,
        "duration": duration,
        "paid": False,
    })
    return dest
