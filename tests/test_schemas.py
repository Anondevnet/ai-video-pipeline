from aiinf.schemas import validate_concept_dict, estimate_beat_seconds, Concept
from aiinf.planner import plan_concepts


def test_plan_concepts_valid_both_lanes():
    concepts = plan_concepts(lane="both", n_per_lane=1)
    assert len(concepts) == 2
    lanes = {c.lane for c in concepts}
    assert lanes == {"fresh_trending", "evergreen"}
    for c in concepts:
        assert c.validate() == []


def test_concept_schema_fields():
    c = plan_concepts(lane="evergreen", n_per_lane=1)[0]
    d = c.to_dict()
    for f in ["hook", "premise", "beats", "visual_direction", "voiceover", "caption", "target_emotion", "trend_relevance", "replay_potential", "share_potential"]:
        assert d[f] not in (None, "", [])


def test_estimate_beat_seconds():
    assert estimate_beat_seconds({"seconds": "0-4"}) == 4
    assert estimate_beat_seconds({"seconds": "14-20"}) == 6


def test_validate_concept_dict_missing():
    errs = validate_concept_dict({"id": "x"})
    assert errs
