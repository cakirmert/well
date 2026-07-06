from __future__ import annotations

import unittest

from wellpass_sync.gui import _friendly_log_line


class GuiLogTests(unittest.TestCase):
    def test_sync_output_is_reworded_for_normal_users(self):
        self.assertEqual(
            _friendly_log_line("Loaded 20 candidate email(s) from graph."),
            "Checked 20 recent email(s).",
        )
        self.assertEqual(
            _friendly_log_line("DRY-RUN would create: Pilates at 2026-07-03 09:00"),
            "Would add: Pilates at 2026-07-03 09:00",
        )
        self.assertEqual(
            _friendly_log_line("SKIP unchanged: Pilates at 2026-07-03 09:00"),
            "Already up to date: Pilates at 2026-07-03 09:00",
        )
        self.assertEqual(
            _friendly_log_line("Summary: scanned=20 parsed=18 created=1 updated=2 cancelled=3 skipped=4 ignored=1 errors=0"),
            "Done: checked 20, understood 18, added 1, updated 2, removed 3, skipped 4.",
        )


if __name__ == "__main__":
    unittest.main()
