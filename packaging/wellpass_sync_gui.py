from __future__ import annotations

import sys

from wellpass_sync.__main__ import main as cli_main
from wellpass_sync.gui import main as gui_main


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit(cli_main(sys.argv[1:]))
    raise SystemExit(gui_main())
