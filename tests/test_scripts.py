from aiinf.planner import plan_concepts
from aiinf.scripts import generate_hook, generate_script, generate_caption


def test_script_generation_structure():
    c = plan_concepts(lane="evergreen", n_per_lane=1)[0]
    s = generate_script(c)
    assert s["concept_id"] == c.id
    assert len(s["lines"]) == len(c.beats)
    for line in s["lines"]:
        assert {"seconds", "action", "on_screen_text"} <= set(line)


def test_hook_and_caption():
    c = plan_concepts(lane="fresh_trending", n_per_lane=1)[0]
    assert generate_hook(c) == c.hook
    cap = generate_caption(c)
    assert isinstance(cap, str) and len(cap) > 5
