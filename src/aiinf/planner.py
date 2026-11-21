import hashlib
import json
import random
from pathlib import Path

from .paths import CONFIG, TRENDS
from .schemas import Concept, Beat

HOOK_TEMPLATES = [
    "POV: you finally moved real this year",
    "Nobody asked, but here's the truth",
    "This beat changed the whole room",
    "Fake energy gets exposed in 3 seconds",
    "Run it back? We run it louder",
]

PREMISE_TEMPLATES = [
    "Zyra Rex breaks down {topic} with raw energy",
    "Zyra Rex calls out {topic} then drops the real take",
    "Zyra Rex turns {topic} into a hype moment",
]

TOPIC_FRESH = ["sped-up beats", "studio freestyles", "this week's sound", "viral transitions"]
TOPIC_EVERGREEN = ["leveling up broke", "cooking in the lab", "real vs fake flex", "hustling with heart", "anthem season energy"]
EMOTIONS = ["hype", "confidence", "triumphant", "defiant", "joyful"]
CTAS = ["Follow for daily bars", "Drop your take below", "Save this for later", ""]


def _rng(seed: str) -> random.Random:
    return random.Random(int(hashlib.sha256(seed.encode()).hexdigest(), 16))


def load_trends(path: Path | None = None) -> list[dict]:
    path = path or TRENDS / "trends.json"
    if not Path(path).exists():
        return []
    return json.loads(Path(path).read_text())


def plan_concepts(lane: str = "both", n_per_lane: int = 2, trends: list[dict] | None = None) -> list[Concept]:
    trends = load_trends() if trends is None else trends
    lanes = ["fresh_trending", "evergreen"] if lane == "both" else [lane]
    concepts = []
    for ln in lanes:
        for i in range(n_per_lane):
            seed = f"{ln}-{i}-2026-10"
            rng = _rng(seed)
            topic_pool = TOPIC_FRESH if ln == "fresh_trending" else TOPIC_EVERGREEN
            topic = rng.choice(topic_pool)
            trend_label = next((t["label"] for t in trends if t.get("lane") == ln), topic)
            cid = f"{ln.replace('_', '-')}-{i+1:03d}"
            beats = [
                {"index": 0, "seconds": "0-3", "action": "Cold open hook, direct to camera", "visual": "violet-lit stage, magenta rim light", "on_screen_text": HOOK_TEMPLATES[i % len(HOOK_TEMPLATES)]},
                {"index": 1, "seconds": "3-8", "action": f"Premise: Zyra breaks down {topic}", "visual": "violet-lit studio", "on_screen_text": topic.upper()},
                {"index": 2, "seconds": "8-14", "action": "Payoff beat, delivery lands", "visual": "chrome-accented close-up on ZR pendant", "on_screen_text": ""},
                {"index": 3, "seconds": "14-20", "action": "CTA + catchphrase sign-off", "visual": "stage pull-back", "on_screen_text": "ZYRA RUN IT BACK"},
            ]
            voiceover = (
                f"{HOOK_TEMPLATES[i % len(HOOK_TEMPLATES)]}. Zyra Rex on {topic}. "
                f"Fake the trick, they feel it. That's real paper energy."
            )
            c = Concept(
                id=cid,
                title=f"Zyra Rex on {topic}",
                lane=ln,
                hook=beats[0]["on_screen_text"],
                premise=PREMISE_TEMPLATES[i % len(PREMISE_TEMPLATES)].format(topic=topic),
                beats=beats,
                visual_direction="violet-lit stage -> studio -> chrome close-up -> stage pull-back; black + violet + chrome grade; consistent character",
                voiceover=voiceover,
                on_screen_text=[b["on_screen_text"] for b in beats if b["on_screen_text"]],
                caption=f"{topic.title()} hits different with Zyra Rex. {rng.choice(CTAS)} #hiphop #shorts",
                target_emotion=rng.choice(EMOTIONS),
                trend_relevance=trend_label if ln == "fresh_trending" else "evergreen",
                replay_potential="high",
                share_potential="high",
                cta=rng.choice([c for c in CTAS if c]),
            )
            errs = c.validate()
            if errs:
                raise ValueError(f"concept {cid} invalid: {errs}")
            concepts.append(c)
    return concepts
