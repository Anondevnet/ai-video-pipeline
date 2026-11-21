from aiinf.state import load_state, save_state, advance, stage_index


def test_state_roundtrip_and_advance(tmp_path):
    p = tmp_path / "state.json"
    s = load_state(p)
    assert s["last_stage"] == "init"
    advance(s, "c1", "planned", {"concept": "x.json"})
    advance(s, "c1", "rendered", {"render": "r.mp4"})
    save_state(s, p)
    s2 = load_state(p)
    assert s2["concepts"]["c1"]["last_stage"] == "rendered"
    assert s2["concepts"]["c1"]["artifacts"]["render"] == "r.mp4"
    assert stage_index("rendered") > stage_index("planned")


def test_state_corrupt_returns_default(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{not json")
    s = load_state(p)
    assert s["last_stage"] == "init"
