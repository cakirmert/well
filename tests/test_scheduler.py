from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wellpass_sync import scheduler


class SchedulerTests(unittest.TestCase):
    def test_frozen_scheduler_uses_executable_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            exe = Path(temp_dir) / "WellpassCalendarSync.exe"
            exe.write_text("", encoding="utf-8")

            with mock.patch.object(scheduler.sys, "frozen", True, create=True), mock.patch.object(
                scheduler.sys, "executable", str(exe)
            ):
                self.assertEqual(scheduler._working_directory(), exe.parent.resolve())
                self.assertEqual(
                    scheduler._sync_command(Path("config.env"), write=True),
                    [str(exe), "run-once", "--env", "config.env", "--write"],
                )


if __name__ == "__main__":
    unittest.main()
