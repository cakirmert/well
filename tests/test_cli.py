from __future__ import annotations

import unittest
from unittest import mock

from wellpass_sync import __main__ as cli


class BrokenStream:
    def reconfigure(self, **_kwargs) -> None:
        return None

    def write(self, _value: str) -> int:
        raise OSError(22, "Invalid argument")

    def flush(self) -> None:
        return None


class CliTests(unittest.TestCase):
    def test_configure_stdio_replaces_broken_windowed_exe_streams(self):
        with mock.patch.object(cli.sys, "stdout", BrokenStream()), mock.patch.object(cli.sys, "stderr", None):
            cli._configure_stdio()

            self.assertNotIsInstance(cli.sys.stdout, BrokenStream)
            self.assertIsNotNone(cli.sys.stderr)
            cli.sys.stdout.write("ok")
            cli.sys.stderr.write("ok")
            cli.sys.stdout.close()
            cli.sys.stderr.close()


if __name__ == "__main__":
    unittest.main()
