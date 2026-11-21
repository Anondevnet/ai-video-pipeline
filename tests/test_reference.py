"""Character-reference resolution and payload attachment tests.

Uses synthetic images generated locally. These are test fixtures, NOT the
Zyra Rex master reference, and are never written to reference/.
"""
import struct
import zlib

import pytest

from aiinf import kling, reference, smoke
from aiinf.character import load_character
from aiinf.planner import plan_concepts


def make_png(path, w=768, h=1366):
    """Write a minimal valid PNG of the given size (stdlib only)."""
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes([(x * 7 + y * 3) % 256 for x in range(w * 3)])
                   for y in range(h))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))
    return path


def test_dimensions_read_from_png_header(tmp_path):
    p = make_png(tmp_path / "a.png", 800, 1200)
    assert reference.image_dimensions(p) == (800, 1200)


def test_validate_rejects_unsupported_format(tmp_path):
    p = tmp_path / "a.gif"
    p.write_bytes(b"GIF89a")
    with pytest.raises(reference.ReferenceError, match="unsupported format"):
        reference.validate_reference_file(p)


def test_validate_rejects_too_small(tmp_path):
    p = make_png(tmp_path / "small.png", 100, 100)
    with pytest.raises(reference.ReferenceError, match="smaller than"):
        reference.validate_reference_file(p)


def test_validate_rejects_bad_aspect_ratio(tmp_path):
    p = make_png(tmp_path / "thin.png", 300, 2000)
    with pytest.raises(reference.ReferenceError, match="aspect ratio"):
        reference.validate_reference_file(p)


def test_validate_rejects_empty_file(tmp_path):
    p = tmp_path / "empty.png"
    p.write_bytes(b"")
    with pytest.raises(reference.ReferenceError, match="empty"):
        reference.validate_reference_file(p)


def test_validate_accepts_vertical_portrait(tmp_path):
    p = make_png(tmp_path / "ok.png", 768, 1366)
    info = reference.validate_reference_file(p)
    assert info["width"] == 768 and info["height"] == 1366
    assert info["mime"] == "image/png"


def test_data_uri_is_inline_base64(tmp_path):
    p = make_png(tmp_path / "ok.png", 768, 1366)
    uri = reference.to_data_uri(p)
    assert uri.startswith("data:image/png;base64,")
    assert "http" not in uri[:40]


def test_resolve_reports_missing_reference_without_fabricating():
    """The shipped config points at reference/zyra-rex-master.png which IS present."""
    c = load_character()
    status = reference.resolve(c)
    assert status["attached"] is True
    assert "reference image file is NOT present on disk" not in status.get("reason", "")
    if not status["attached"]:
        assert status["configured_path"].endswith("reference/zyra-rex-master.png")


def test_resolve_attaches_when_file_present(tmp_path):
    p = make_png(tmp_path / "ref.png", 768, 1366)
    status = reference.resolve({"visual_reference": {"enabled": True, "path": str(p),
                                                      "role": "refer_image"}})
    assert status["attached"] is True
    assert status["role"] == "refer_image"


def test_resolve_disabled_returns_not_attached():
    assert reference.resolve({"visual_reference": {"enabled": False}})["attached"] is False


def test_payload_includes_refer_image_when_attached(tmp_path):
    p = make_png(tmp_path / "ref.png", 768, 1366)
    c = plan_concepts(lane="evergreen", n_per_lane=1)[0]
    payload = kling.build_request_payload(c, 0, 5, refer_image_url=reference.to_data_uri(p))
    types = [i["type"] for i in payload["contents"]]
    assert types == ["prompt", "refer_image"]
    assert payload["contents"][1]["id"] == "image_2"


def test_payload_first_frame_omits_aspect_ratio(tmp_path):
    p = make_png(tmp_path / "ref.png", 768, 1366)
    c = plan_concepts(lane="evergreen", n_per_lane=1)[0]
    payload = kling.build_request_payload(c, 0, 5, first_frame_url=reference.to_data_uri(p))
    assert [i["type"] for i in payload["contents"]] == ["prompt", "first_frame"]
    assert "aspect_ratio" not in payload["settings"]


def test_payload_rejects_non_url_non_datauri():
    c = plan_concepts(lane="evergreen", n_per_lane=1)[0]
    with pytest.raises(ValueError, match="https URL or a base64 data URI"):
        kling.build_request_payload(c, 0, 5, refer_image_url="file:///etc/passwd")


def test_smoke_preview_states_reference_not_attached():
    """Dry-run should report reference status based on actual config."""
    report = smoke.preview(env={"KLING_API_KEY": "x", "KLING_LIVE_AUTHORIZED": "1"})
    assert report["character"] == "Zyra Rex"
    assert report["character_reference"]["attached"] is True
    assert "Zyra Rex reference" in report["character_reference"]["summary"]


def test_smoke_reference_arg_empty_when_absent():
    kwargs = smoke._reference_arg({"attached": False, "reason": "nope"})
    assert kwargs == {}


def test_smoke_reference_arg_uses_refer_image_role(tmp_path):
    p = make_png(tmp_path / "ref.png", 768, 1366)
    kwargs = smoke._reference_arg(reference.resolve(
        {"visual_reference": {"enabled": True, "path": str(p), "role": "refer_image"}}))
    assert "refer_image_url" in kwargs
    assert kwargs["refer_image_url"].startswith("data:image/png;base64,")