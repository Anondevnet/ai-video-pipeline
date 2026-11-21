from .character import load_character
from .schemas import Concept


def generate_hook(concept: Concept, character: dict | None = None) -> str:
    character = character or load_character()
    return concept.hook


def generate_script(concept: Concept, character: dict | None = None) -> dict:
    character = character or load_character()
    lines = []
    for b in concept.beats:
        lines.append({
            "seconds": b["seconds"],
            "voiceover": concept.voiceover if b["index"] == 0 else "",
            "action": b["action"],
            "on_screen_text": b.get("on_screen_text", ""),
        })
    return {"concept_id": concept.id, "character": character["name"], "lines": lines}


def generate_caption(concept: Concept, character: dict | None = None) -> str:
    character = character or load_character()
    catch = character["catchphrases"][0] if character.get("catchphrases") else ""
    return f"{concept.caption}\n\n{catch}".strip()
