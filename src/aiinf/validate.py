import json
import subprocess
from pathlib import Path

TARGET_W, TARGET_H = 1080, 1920
TARGET_FPS = 30


def _ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(out.stdout)


def validate_video(path: Path, require_audio: bool = False) -> list[str]:
    errors = []
    path = Path(path)
    if not path.exists():
        return [f"missing file: {path}"]
    if path.stat().st_size == 0:
        errors.append("empty file")
        return errors
    try:
        meta = _ffprobe(path)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return ["ffprobe failed / corrupt file"]
    v = next((s for s in meta.get("streams", []) if s["codec_type"] == "video"), None)
    if v is None:
        errors.append("no video stream")
        return errors
    w, h = int(v["width"]), int(v["height"])
    if h <= w:
        errors.append(f"not vertical: {w}x{h}")
    fps_str = v.get("avg_frame_rate", "0/1")
    try:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
        if abs(fps - TARGET_FPS) > 1:
            errors.append(f"fps {fps:.2f} != {TARGET_FPS}")
    except (ValueError, ZeroDivisionError):
        errors.append("bad fps")
    dur = float(meta.get("format", {}).get("duration", 0) or 0)
    if dur <= 0:
        errors.append("no duration")
    a = next((s for s in meta.get("streams", []) if s["codec_type"] == "audio"), None)
    if a is None and require_audio:
        errors.append("no audio stream")
    return errors


def validate_render(path: Path, target_duration: int = 20, require_audio: bool = False) -> list[str]:
    errors = validate_video(path, require_audio=require_audio)
    if errors:
        return errors
    meta = _ffprobe(Path(path))
    dur = float(meta["format"]["duration"])
    if abs(dur - target_duration) > 2.0:
        errors.append(f"duration {dur:.1f}s off target {target_duration}s")
    v = next(s for s in meta["streams"] if s["codec_type"] == "video")
    if (int(v["width"]), int(v["height"])) != (TARGET_W, TARGET_H):
        errors.append(f"resolution {v['width']}x{v['height']} != {TARGET_W}x{TARGET_H}")
    return errors
