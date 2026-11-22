"""Regenerate the example MusicXML scores in examples/ (built from tests/scorebuilder.py)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests import scorebuilder as sb  # noqa: E402

EXAMPLES = {
    "simple": (sb.simple_score(), "Simple (4 bars, no structure)"),
    "endings": (sb.endings_score(), "Repeat with 1st/2nd ending"),
    "dal_segno": (sb.dal_segno_score(), "D.S. al Coda (encoded)"),
    "text_jump": (sb.text_only_jump_score(), "D.S. as text only (should warn)"),
}

for name, ((parts, bars), title) in EXAMPLES.items():
    sb.write_score(ROOT / "examples" / f"{name}.musicxml", parts, bars, title=title)
    print("wrote", f"examples/{name}.musicxml")
