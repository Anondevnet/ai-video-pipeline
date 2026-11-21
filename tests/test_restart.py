import json
from pathlib import Path

import pytest

from aiinf import pipeline
from aiinf.state import load_state


@pytest.mark.slow
def test_full_mock_pipeline_and_restart():
    res = pipeline.run_pipeline(lane="evergreen", mock=True)
    assert res["results"], "no concepts processed"
    s = load_state()
    for cid, rec in s["concepts"].items():
        assert rec["last_stage"] == "exported", rec

    # restart: nothing should be regenerated; artifacts unchanged
    before = set(Path("clips").glob("**/*")) | set(Path("renders").glob("**/*"))
    mtimes = {p: p.stat().st_mtime for p in before if p.is_file()}
    res2 = pipeline.run_pipeline(lane="evergreen", mock=True)
    assert all(r["status"] == "ok" for r in res2["results"])
    for p, m in mtimes.items():
        assert p.stat().st_mtime == m, f"regenerated {p}"
