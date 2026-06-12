"""Repository-local launcher for the STAS command-line helper."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from stas_app.main import main


if __name__ == "__main__":
    raise SystemExit(main())
