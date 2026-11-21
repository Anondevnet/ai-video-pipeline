"""Character/style reference image handling for Kling 3.0 Omni.

The official Kling documentation states that for `first_frame`, `last_frame` and
`refer_image` inputs, the ``url`` field accepts either a URL **or base64**:
"The input content can be provided through URL or base64".

That means a local reference image can be supplied inline as a base64 data URI
without uploading it to any external host. No Element ID is required or
fabricated here.

Official constraints enforced below:
  * format must be .jpg, .jpeg or .png
  * file size must not exceed 50MB
  * width/height must each be at least 300px
  * aspect ratio must be between 1:2.5 and 2.5:1

Only the standard library is used (dimensions are read from file headers).
"""
import base64
import struct
from pathlib import Path

from .paths import ROOT

MAX_BYTES = 50 * 1024 * 1024
MIN_DIM = 300
MIN_ASPECT = 1 / 2.5
MAX_ASPECT = 2.5
ALLOWED_SUFFIXES = (".png", ".jpg", ".jpeg")
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class ReferenceError(RuntimeError):
    pass


def _png_size(data: bytes):
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    if data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def _jpeg_size(data: bytes):
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                      0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + seg_len
    return None


def image_dimensions(path: Path):
    data = Path(path).read_bytes()
    return _png_size(data) or _jpeg_size(data)


def validate_reference_file(path: Path) -> dict:
    """Validate a local reference image against the documented Kling constraints."""
    path = Path(path)
    if not path.exists():
        raise ReferenceError(f"reference image not found: {path}")
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise ReferenceError(
            f"unsupported format '{path.suffix}'; Kling accepts .jpg, .jpeg, .png")
    size = path.stat().st_size
    if size == 0:
        raise ReferenceError(f"reference image is empty: {path}")
    if size > MAX_BYTES:
        raise ReferenceError(f"reference image {size} bytes exceeds 50MB limit")
    dims = image_dimensions(path)
    if not dims:
        raise ReferenceError(f"could not read image dimensions from {path}")
    w, h = dims
    if w < MIN_DIM or h < MIN_DIM:
        raise ReferenceError(f"image {w}x{h} is smaller than the {MIN_DIM}px minimum")
    ratio = w / h
    if not (MIN_ASPECT <= ratio <= MAX_ASPECT):
        raise ReferenceError(f"image aspect ratio {ratio:.2f} outside 1:2.5 - 2.5:1")
    return {"path": str(path), "bytes": size, "width": w, "height": h,
            "aspect_ratio": round(ratio, 3), "mime": MIME[path.suffix.lower()]}


def to_data_uri(path: Path) -> str:
    """Encode a local image as a base64 data URI (officially accepted by Kling)."""
    path = Path(path)
    info = validate_reference_file(path)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{info['mime']};base64,{encoded}"


def resolve(character: dict) -> dict:
    """Resolve the configured visual reference for a character spec.

    Returns a status dict; never raises, so callers can report a precise,
    non-fabricated description of what is and is not attached.
    """
    cfg = (character or {}).get("visual_reference") or {}
    if not cfg.get("enabled"):
        return {"attached": False, "reason": "visual_reference.enabled is false"}

    raw = cfg.get("path")
    if not raw:
        return {"attached": False, "reason": "no visual_reference.path configured"}

    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return {
            "attached": False,
            "configured_path": str(path),
            "role": cfg.get("role", "refer_image"),
            "reason": ("reference image file is NOT present on disk; "
                       "no image is attached to the Kling request"),
        }
    try:
        info = validate_reference_file(path)
    except ReferenceError as exc:
        return {"attached": False, "configured_path": str(path), "reason": str(exc)}
    return {"attached": True, "role": cfg.get("role", "refer_image"), **info}