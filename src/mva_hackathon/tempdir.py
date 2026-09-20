"""Temporary directories that do not fail closed on Windows cleanup locks.

Scientific results are captured before directory deletion. WinError 32 during
rmtree is the indexer or antivirus holding a just-written file, not a failed
gate and not a rescued child.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any


class TemporaryDirectory(tempfile.TemporaryDirectory):
    _mva_ignore_windows_cleanup = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if os.name == "nt":
            kwargs.setdefault("ignore_cleanup_errors", True)
        super().__init__(*args, **kwargs)


def install_windows_safe_tempfile() -> None:
    if getattr(tempfile.TemporaryDirectory, "_mva_ignore_windows_cleanup", False):
        return
    tempfile.TemporaryDirectory = TemporaryDirectory
