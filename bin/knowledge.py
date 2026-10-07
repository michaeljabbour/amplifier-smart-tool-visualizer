#!/usr/bin/env python3
"""Run the knowledge tool from a checkout without installing it."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from knowledge.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
