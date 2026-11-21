import json

from aiinf.character import load_character, load_strategy


def test_character_loads_and_validates():
    c = load_character()
    assert c["name"] == "Zyra Rex"
    assert c["handle"] == "@zyrarex"
    assert c["real_person"] is False
    for f in ["visual_identity", "personality", "voice_persona", "content_pillars", "differentiation"]:
        assert c[f]


def test_character_matches_zyra_rex_direction():
    c = load_character()
    blob = json.dumps(c).lower()
    for term in ["zyra rex", "violet", "chrome", "zr pendant", "medium-brown"]:
        assert term in blob, f"missing Zyra Rex direction: {term}"
    assert "not reproduce any real person" in c["visual_reference"]["note"]


def test_zyra_personality_traits():
    c = load_character()
    blob = (c["personality"] + " " + " ".join(c["content_pillars"])).lower()
    for trait in ["confident", "funny", "ambitious", "cocky", "unpredictable", "hip-hop"]:
        assert trait in blob


def test_strategy_targets():
    s = load_strategy()
    assert s["target_duration_seconds"] == 20
    assert s["target_resolution"] == [1080, 1920]
    assert s["model"] == "kling-3.0-omni"
