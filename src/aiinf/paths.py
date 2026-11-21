from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLIPS = ROOT / "clips"
FRAMES = ROOT / "frames"
LOGS = ROOT / "logs"
REFERENCE = ROOT / "reference"
RENDERS = ROOT / "renders"
EXPORTS = ROOT / "exports"
SMOKES = ROOT / "smokes"
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "pipeline_state.json"
CONFIG = ROOT / "config"
TRENDS = ROOT / "trends"
TESTS = ROOT / "tests"
