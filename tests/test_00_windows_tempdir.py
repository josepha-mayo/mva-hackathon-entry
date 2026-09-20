"""Install Windows tempfile cleanup safety before later discover modules."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mva_hackathon.tempdir import (
    TemporaryDirectory,
    install_windows_safe_tempfile,
)

install_windows_safe_tempfile()


class WindowsTempdirTests(unittest.TestCase):
    def test_install_is_idempotent_and_writes(self) -> None:
        install_windows_safe_tempfile()
        install_windows_safe_tempfile()
        with TemporaryDirectory() as folder:
            probe = Path(folder) / "probe.txt"
            probe.write_text("synthetic\n", encoding="utf-8")
            self.assertEqual(probe.read_text(encoding="utf-8"), "synthetic\n")

    def test_windows_ignores_cleanup_errors_by_default(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows cleanup lock only")
        workspace = TemporaryDirectory()
        self.assertTrue(workspace._ignore_cleanup_errors)
        workspace.cleanup()
        self.assertTrue(
            getattr(tempfile.TemporaryDirectory, "_mva_ignore_windows_cleanup", False)
        )
