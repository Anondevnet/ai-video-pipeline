import json
import re
from pathlib import Path

SAFE = re.compile(r"[^a-zA-Z0-9_-]+")


def slugify(s: str) -> str:
    return SAFE.sub("-", s).strip("-").lower()


def concept_slug(concept_id: str) -> str:
    return slugify(concept_id)


def clip_path(clips_dir: Path, concept_id: str, index: int) -> Path:
    return Path(clips_dir) / f"{concept_slug(concept_id)}-clip{index}.mp4"


def clip_meta_path(clips_dir: Path, concept_id: str, index: int) -> Path:
    return Path(clips_dir) / f"{concept_slug(concept_id)}-clip{index}.json"


def render_path(renders_dir: Path, concept_id: str) -> Path:
    return Path(renders_dir) / f"{concept_slug(concept_id)}-final.mp4"


def write_metadata(path: Path, meta: dict) -> Path:
    path = Path(path)
    path.write_text(json.dumps(meta, indent=2, sort_keys=True))
    return path


def read_metadata(path: Path) -> dict:
    return json.loads(Path(path).read_text())
