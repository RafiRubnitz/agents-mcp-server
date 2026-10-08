"""Runs the hook manager from the plugin's own files: `python run_hook.py <event>`.

The plugin is not pip-installed, so its `src/` is put on the path here. The plugin's
hooks.json starts this with `uv run --no-project --with loguru`, which supplies the hook
manager's only third-party dependency.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inbox_mcp.hook import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
