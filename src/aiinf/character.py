import json
from pathlib import Path

from .paths import CONFIG

REQUIRED_FIELDS = [
    "name", "handle", "visual_identity", "personality", "voice_persona",
    "recurring_themes", "wardrobe_style", "visual_continuity_rules",
    "behavior_rules", "content_pillars", "audience", "differentiation",
]


def load_character(path: Path | None = None) -> dict:
    path = path or CONFIG / "character.json"
    data = json.loads(Path(path).read_text())
    missing = [f for f in REQUIRED_FIELDS if not data.get(f)]
    if missing:
        raise ValueError(f"character spec missing fields: {missing}")
    if data.get("real_person") is not False:
        raise ValueError("character must be explicitly non-real-person")
    return data


def load_strategy(path: Path | None = None) -> dict:
    path = path or CONFIG / "strategy.json"
    return json.loads(Path(path).read_text())
