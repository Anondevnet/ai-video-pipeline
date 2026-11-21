import subprocess
from pathlib import Path

from . import assets
from .paths import CLIPS, RENDERS


def render_from_clips(concept_id: str, clips_dir: Path = CLIPS, renders_dir: Path = RENDERS,
                      expected: int = 4, clip_duration: int = 5) -> Path:
    clips_dir, renders_dir = Path(clips_dir), Path(renders_dir)
    clips = [assets.clip_path(clips_dir, concept_id, i) for i in range(expected)]
    missing = [str(p) for p in clips if not p.exists()]
    if missing:
        raise FileNotFoundError(f"missing clips: {missing}")
    renders_dir.mkdir(parents=True, exist_ok=True)
    out = assets.render_path(renders_dir, concept_id)
    inputs = []
    for c in clips:
        inputs += ["-i", str(c)]
    parts = []
    for i in range(expected):
        parts.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30[v{i}]"
        )
    concat_in = "".join(f"[v{i}][{i}:a]" for i in range(expected))
    parts.append(f"{concat_in}concat=n={expected}:v=1:a=1[v][a]")
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(parts),
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    assets.write_metadata(out.with_suffix(".json"), {
        "concept_id": concept_id, "clips": [str(c) for c in clips], "duration_target": expected * clip_duration,
        "generator": "aiinf-render",
    })
    return out
