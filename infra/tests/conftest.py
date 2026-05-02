"""Make the `stacks` package importable when pytest runs from the repo root."""

from __future__ import annotations

import sys
from pathlib import Path

_infra_root = Path(__file__).resolve().parents[1]
if str(_infra_root) not in sys.path:
    sys.path.insert(0, str(_infra_root))
