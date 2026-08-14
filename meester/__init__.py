"""Meester - a job-application autopilot."""

import sys

# 3.9 is the floor because that is what macOS ships as `python3`, and requiring
# anything newer would force a Homebrew install on every Mac for no real benefit:
# every annotated module carries `from __future__ import annotations`, and
# nothing here uses match statements or runtime unions.
#
# Rather than trust that reasoning, scripts/setup_mac.sh runs
# scripts/smoke_test.py against whichever interpreter it picks and only proceeds
# if a real path through every module works.
if sys.version_info < (3, 9):
    raise RuntimeError(
        f"Meester needs Python 3.9 or newer, but is running on "
        f"{sys.version_info.major}.{sys.version_info.minor}. "
        "On macOS: brew install python@3.12, then re-run scripts/setup_mac.sh"
    )

__version__ = "0.1.0"
