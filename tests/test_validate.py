import subprocess
from pathlib import Path

from aiinf.validate import validate_video, validate_render


def _mk(path: Path, w: int, h: int, dur: int, audio: bool):
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=30:duration={dur}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100", "-c:a", "aac", "-shortest"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


def test_validate_video_vertical_ok(tmp_path):
    p = tmp_path / "v.mp4"
    _mk(p, 720, 1280, 5, True)
    assert validate_video(p, require_audio=True) == []


def test_validate_video_horizontal_flagged(tmp_path):
    p = tmp_path / "v.mp4"
    _mk(p, 1280, 720, 5, True)
    errs = validate_video(p)
    assert any("vertical" in e for e in errs)


def test_validate_video_missing_audio_flagged(tmp_path):
    p = tmp_path / "v.mp4"
    _mk(p, 720, 1280, 5, False)
    errs = validate_video(p, require_audio=True)
    assert any("audio" in e for e in errs)


def test_validate_render_resolution(tmp_path):
    p = tmp_path / "r.mp4"
    _mk(p, 720, 1280, 20, True)
    errs = validate_render(p, target_duration=20)
    assert any("resolution" in e for e in errs)
    p2 = tmp_path / "r2.mp4"
    _mk(p2, 1080, 1920, 20, True)
    assert validate_render(p2, target_duration=20) == []


def test_validate_missing_file(tmp_path):
    assert validate_video(tmp_path / "nope.mp4")
