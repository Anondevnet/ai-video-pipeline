"""Live-mode safety tests. No Kling requests are made: the network path is
monkeypatched away and every failure is simulated locally."""
import pathlib
import tempfile

import pytest

from aiinf import kling, pipeline


def _live_cfg():
    from aiinf.env import KlingConfig
    return KlingConfig(api_key=None, access_key="ak", secret_key="sk",
                       base_url="https://api-singapore.klingai.com",
                       mock=False, live_authorized=True)


def test_live_refuses_mock_artifacts(monkeypatch, tmp_path):
    """A clip produced by the mock generator must never be silently reused in live mode."""
    monkeypatch.setattr(pipeline, "load_kling_config", _live_cfg)
    monkeypatch.setattr(pipeline, "plan_concepts", lambda lane: [_fake_concept("evergreen-901")])
    monkeypatch.setattr(pipeline, "_has_artifacts", lambda cid: False)
    monkeypatch.setattr(pipeline, "_concept_path", lambda cid: tmp_path / cid)
    store = {"schema_version": 1, "last_stage": "init", "concepts": {}, "history": [], "updated_at": ""}
    monkeypatch.setattr(pipeline, "load_state", lambda: store)
    monkeypatch.setattr(pipeline, "save_state", lambda s: None)

    # simulate an existing mock clip for this concept
    clip = pipeline.assets.clip_path(pipeline.CLIPS, "evergreen-901", 0)
    clip.parent.mkdir(parents=True, exist_ok=True)
    clip.write_bytes(b"fake")
    pipeline.assets.write_metadata(clip.with_suffix(".json"), {"generator": pipeline.MOCK_GENERATOR})
    # never reach the network
    def forbidden(*a, **kw):
        raise AssertionError("live request attempted")
    monkeypatch.setattr(kling, "create_task", forbidden)
    try:
        res = pipeline.run_pipeline(lane="evergreen", live=True)
        r = res["results"][0]
        assert r["status"] == "generation_failed"
        assert "MockArtifactConflict" in r["error"]
        assert "will not reuse mock artifacts" in r["error"]
        assert store["concepts"]["evergreen-901"]["last_stage"] != "clips_generated"
    finally:
        clip.unlink()
        clip.with_suffix(".json").unlink()


def test_live_failure_does_not_advance_checkpoint(monkeypatch, tmp_path):
    """A failed create_task must leave the concept short of clips_generated."""
    monkeypatch.setattr(pipeline, "load_kling_config", _live_cfg)
    monkeypatch.setattr(pipeline, "plan_concepts", lambda lane: [_fake_concept("evergreen-777")])
    monkeypatch.setattr(pipeline, "_has_artifacts", lambda cid: False)
    monkeypatch.setattr(pipeline, "_concept_path", lambda cid: tmp_path / cid)
    # isolate state so the real checkpoint file is untouched
    store = {"schema_version": 1, "last_stage": "init", "concepts": {}, "history": [], "updated_at": ""}
    monkeypatch.setattr(pipeline, "load_state", lambda: store)
    monkeypatch.setattr(pipeline, "save_state", lambda s: None)

    def boom(*a, **kw):
        raise kling.KlingError("API error code=1002 message=quota request_id=r1")
    monkeypatch.setattr(kling, "create_task", boom)

    res = pipeline.run_pipeline(lane="evergreen", live=True)
    r = res["results"][0]
    assert r["status"] == "generation_failed"
    assert "quota" in r["error"]
    assert r["stage"] != "clips_generated"

    rec = store["concepts"]["evergreen-777"]
    assert rec["last_stage"] not in ("clips_generated", "rendered", "validated", "exported")
    assert any("quota" in e for e in rec["errors"])


def test_live_requires_unused_concept(monkeypatch):
    """Live mode must refuse when every candidate already has artifacts."""
    monkeypatch.setattr(pipeline, "load_kling_config", _live_cfg)
    monkeypatch.setattr(pipeline, "plan_concepts", lambda lane: [_fake_concept("evergreen-001")])
    monkeypatch.setattr(pipeline, "_has_artifacts", lambda cid: True)
    # no concept qualifies -> refuse before any credential/plan work
    with pytest.raises(RuntimeError, match="refusing live run"):
        pipeline.run_pipeline(lane="evergreen", live=True)


def test_live_defaults_to_single_concept(monkeypatch, tmp_path):
    """Live mode must process exactly one concept even when several are available."""
    monkeypatch.setattr(pipeline, "load_kling_config", _live_cfg)
    monkeypatch.setattr(pipeline, "plan_concepts", lambda lane: [
        _fake_concept("evergreen-701"), _fake_concept("evergreen-702")])
    monkeypatch.setattr(pipeline, "_has_artifacts", lambda cid: False)
    monkeypatch.setattr(pipeline, "_concept_path", lambda cid: tmp_path / cid)
    store = {"schema_version": 1, "last_stage": "init", "concepts": {}, "history": [], "updated_at": ""}
    monkeypatch.setattr(pipeline, "load_state", lambda: store)
    monkeypatch.setattr(pipeline, "save_state", lambda s: None)
    calls = []

    def failing(cfg, concept, i, **kwargs):
        calls.append((concept.id, i))
        raise kling.KlingError("stop here")
    monkeypatch.setattr(kling, "create_task", failing)

    res = pipeline.run_pipeline(lane="evergreen", live=True)
    assert len(res["results"]) == 1
    assert res["results"][0]["concept"] == "evergreen-701"
    assert {c[0] for c in calls} == {"evergreen-701"}


def test_live_rejects_bad_concept_limit(monkeypatch):
    monkeypatch.setattr(pipeline, "load_kling_config", _live_cfg)
    monkeypatch.setattr(pipeline, "plan_concepts", lambda lane: [_fake_concept("evergreen-703")])
    monkeypatch.setattr(pipeline, "_has_artifacts", lambda cid: False)
    with pytest.raises(ValueError):
        pipeline.run_pipeline(lane="evergreen", live=True, concept_limit=0)


def test_mock_never_reuses_live_or_marks_paid():
    """Mock clips are always labeled as non-paid mock artifacts."""
    from aiinf.planner import plan_concepts
    c = plan_concepts(lane="evergreen", n_per_lane=1)[0]
    from aiinf import assets
    with tempfile.TemporaryDirectory() as td:
        dest = pathlib.Path(td) / "x.mp4"
        kling.generate_clip_mock(c, 0, dest, duration=1)
        meta = assets.read_metadata(dest.with_suffix(".json"))
        assert meta["generator"] == pipeline.MOCK_GENERATOR
        assert meta["paid"] is False


def test_concept_limit_truncates_selection():
    """--concept-limit restricts how many concepts a run touches.

    Uses the evergreen fixtures already exported by the mock run, so no media is generated.
    """
    res = pipeline.run_pipeline(lane="evergreen", mock=True, concept_limit=1)
    assert len(res["results"]) == 1
    assert res["results"][0]["status"] == "ok"


def _fake_concept(cid):
    from aiinf.schemas import Concept
    return Concept(
        id=cid, title="t", lane="evergreen", hook="h", premise="p",
        beats=[{"index": i, "seconds": "0-3", "action": "a", "visual": "v", "on_screen_text": ""}
               for i in range(4)],
        visual_direction="vd", voiceover="vo", on_screen_text=["h"], caption="c",
        target_emotion="hype", trend_relevance="e", replay_potential="high",
        share_potential="high",
    )