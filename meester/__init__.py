"""Meester - a job-application autopilot."""

import sys

# macOS still ships Python 3.9 as `python3`. This package runs on 3.10+ and is
# tested on 3.11. Failing here with a clear message beats a confusing
# TypeError somewhere deep in a dataclass an hour into an unattended run.
if sys.version_info < (3, 10):
    raise RuntimeError(
        f"Meester needs Python 3.10 or newer, but is running on "
        f"{sys.version_info.major}.{sys.version_info.minor}. "
        "On macOS: brew install python@3.12, then re-run scripts/setup_mac.sh"
    )

__version__ = "0.1.0"
