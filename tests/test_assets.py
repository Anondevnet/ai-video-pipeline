from pathlib import Path
from aiinf import assets


def test_slug_and_paths():
    assert assets.slugify("Fresh Trending 001!") == "fresh-trending-001"
    p = assets.clip_path(Path("/tmp/clips"), "Fresh Trending 001", 2)
    assert p.name == "fresh-trending-001-clip2.mp4"
    assert assets.render_path(Path("/tmp/r"), "abc").name == "abc-final.mp4"


def test_metadata_roundtrip(tmp_path):
    p = assets.write_metadata(tmp_path / "m.json", {"a": 1})
    assert assets.read_metadata(p) == {"a": 1}
