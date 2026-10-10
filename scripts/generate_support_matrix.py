"""Write docs/support_matrix.md from the decoding profiles.

Run from the repository root with the test environment active:

    python scripts/generate_support_matrix.py

``tests/test_support_matrix.py`` fails when the committed file no longer
matches the profiles, so this has to be re-run after touching them.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from custom_components.aseko_local.decoding.support_matrix import render  # noqa: E402

TARGET = ROOT / "docs" / "support_matrix.md"

if __name__ == "__main__":
    TARGET.write_text(render(), encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT)}")
