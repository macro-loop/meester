#!/usr/bin/env bash
# Sets up a clone for EDITING Meester, not for running her job search.
#
# The difference matters. scripts/setup_mac.sh installs launchd agents, downloads
# a 150 MB browser and puts a shortcut on the Desktop, because it is setting up
# the machine that does the work. This script does none of that. It builds a venv
# that can run the tests, turns on the pre-push gate, and stops.
#
# Safe to re-run.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.meester.harvest.plist"

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31m error:\033[0m %s\n' "$*" >&2; exit 1; }

# --- 0. Refuse to run inside production ---------------------------------------
# If the scheduled job runs from this very folder, this is her live checkout.
# Editing here dirties the tree, which silently disables both `git pull --ff-only`
# in run_harvest.sh and the "Update available" button in the app - and the hourly
# job would execute half-finished code, including real job applications.
if [[ -f "$PLIST" ]] && grep -q "<string>$REPO/scripts/run_harvest.sh</string>" "$PLIST" 2>/dev/null; then
  die "this folder is the one the scheduled job runs from - it is production.

  Do not edit here. Clone a second copy and set that one up instead:

      git clone https://github.com/macro-loop/meester.git ~/meester-dev
      cd ~/meester-dev && ./scripts/setup_dev.sh

  See docs/MAINTAINING.md."
fi

# --- 1. Python ----------------------------------------------------------------
find_python() {
  for c in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then
      command -v "$c"; return 0
    fi
  done
  return 1
}

say "Looking for Python 3.9+"
PY_BIN="$(find_python)" || die "no Python 3.9+ found. Install one:  brew install python@3.12"
say "Using $PY_BIN ($("$PY_BIN" --version))"

# --- 2. Virtualenv ------------------------------------------------------------
# Required, not optional: recent macOS and Homebrew Pythons are externally
# managed (PEP 668) and refuse a plain `pip install`.
say "Creating virtualenv at .venv"
"$PY_BIN" -m venv "$REPO/.venv"
"$REPO/.venv/bin/python" -m pip install --quiet --upgrade pip
"$REPO/.venv/bin/python" -m pip install --quiet -r "$REPO/requirements.txt" -r "$REPO/requirements-dev.txt"
say "Dependencies installed (including pytest)"

# Deliberately NOT installing the chromium browser. The apply-engine tests
# monkeypatch sync_playwright, so the package needs to import but the 150 MB
# download is never exercised here - and the dev clone must never run
# apply-run --live anyway.

# --- 3. The push gate ---------------------------------------------------------
# core.hooksPath is per-clone local config and does not travel with a clone, so
# a fresh checkout is ungated until someone sets this. That someone is this line.
git -C "$REPO" config core.hooksPath scripts/githooks
say "Pre-push checks enabled"

# --- 4. Prove the toolchain actually works ------------------------------------
# Finding out that pytest cannot run here at `git push` time, with a change ready
# to ship, is the wrong moment.
say "Running the test suite once to prove this setup works"
if ! "$REPO/.venv/bin/python" -m pytest "$REPO/tests/" -q; then
  die "the tests do not pass in this fresh checkout. Do not start editing yet."
fi

cat <<EOF

  Ready. This is your editing copy - nothing here runs on a schedule.

  Make a change:      cd $REPO && claude
  Test by hand:       .venv/bin/python -m pytest tests/ -q
  See it on screen:   .venv/bin/python -m meester serve --port 8766
  Ship it:            git add -A && git commit -m "what changed" && git push

  Full instructions:  docs/MAINTAINING.md

EOF
