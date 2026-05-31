"""Entry point when running the repo root (e.g. python main.py). Delegates to CLI."""

import sys
from pathlib import Path

# Allow running without installing: add src so game_images is importable
_root = Path(__file__).resolve().parent
_src = _root / "src"
if _src.exists() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from game_images.cli import main

if __name__ == "__main__":
    main()
