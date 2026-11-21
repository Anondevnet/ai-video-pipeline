from dataclasses import dataclass, field, asdict
from typing import Any

LANES = ("fresh_trending", "evergreen")
REQUIRED_CONCEPT_FIELDS = [
    "id", "title", "lane", "hook", "premise", "beats", "visual_direction",
    "voiceover", "on_screen_text", "caption", "target_emotion",
    "trend_relevance", "replay_potential", "share_potential",
]


@dataclass
class Beat:
    index: int
    seconds: str
    action: str
    visual: str
    on_screen_text: str = ""


@dataclass
class Concept:
    id: str
    title: str
    lane: str
    hook: str
    premise: str
    beats: list[dict]
    visual_direction: str
    voiceover: str
    on_screen_text: list[str]
    caption: str
    target_emotion: str
    trend_relevance: str
    replay_potential: str
    share_potential: str
    cta: str = ""
    duration_target: int = 20

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def validate(self) -> list[str]:
        errors = []
        if self.lane not in LANES:
            errors.append(f"bad lane: {self.lane}")
        if len(self.beats) < 3:
            errors.append("need >= 3 beats")
        for f in REQUIRED_CONCEPT_FIELDS:
            if getattr(self, f, None) in (None, "", []):
                errors.append(f"missing {f}")
        total = sum(estimate_beat_seconds(b) for b in self.beats)
        if not (12 <= total <= 26):
            errors.append(f"beat seconds sum {total}s outside 12-26s")
        return errors


def estimate_beat_seconds(beat: dict) -> int:
    s = str(beat.get("seconds", "0-4")).split("-")
    try:
        return int(float(s[-1])) - int(float(s[0]))
    except (ValueError, IndexError):
        return 0


def validate_concept_dict(d: dict) -> list[str]:
    errors = []
    for f in REQUIRED_CONCEPT_FIELDS:
        if f not in d or d[f] in (None, "", []):
            errors.append(f"missing {f}")
    if d.get("lane") not in LANES:
        errors.append("bad lane")
    if isinstance(d.get("beats"), list) and len(d["beats"]) < 3:
        errors.append("need >= 3 beats")
    return errors
