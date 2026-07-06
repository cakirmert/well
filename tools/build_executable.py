from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Wellpass Calendar Sync GUI executable.")
    parser.add_argument("--name", default="WellpassCalendarSync")
    parser.add_argument("--onedir", action="store_true", help="Build a folder instead of a single executable.")
    parser.add_argument("--console", action="store_true", help="Keep a console window attached.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    launcher = root / "packaging" / "wellpass_sync_gui.py"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name",
        args.name,
        "--clean",
        "--collect-submodules",
        "caldav",
        "--collect-submodules",
        "googleapiclient",
        "--collect-submodules",
        "google_auth_oauthlib",
        "--collect-submodules",
        "keyring.backends",
        "--collect-submodules",
        "win32ctypes.core",
        "--collect-submodules",
        "win32ctypes.pywin32",
        "--collect-data",
        "tzdata",
        "--hidden-import",
        "win32cred",
    ]
    command.append("--onedir" if args.onedir else "--onefile")
    if not args.console:
        command.append("--windowed")
    command.append(str(launcher))

    subprocess.run(command, cwd=root, check=True)
    print(f"Build output is in: {root / 'dist'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
