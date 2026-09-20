"""Install Windows tempfile cleanup safety when tests load as a package."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import mva_hackathon.tempdir as mva_tempdir

mva_tempdir.install_windows_safe_tempfile()
