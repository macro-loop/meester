#!/usr/bin/env bash
# One-shot setup for the MacBook that runs Meester.
# Safe to re-run: it is idempotent and will reinstall/reload cleanly.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.meester.harvest"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
INTERVAL="${MEESTER_INTERVAL:-3600}"   # seconds between runs

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33m warning:\033[0m %s\n' "$*"; }
die() { printf '\033[31m error:\033[0m %s\n' "$*" >&2; exit 1; }

# --- 1. Python ----------------------------------------------------------------
# macOS still ships an old system Python. Find a real one rather than silently
# half-working on 3.9.
# Prefer a newer interpreter if one is installed, but accept the 3.9 that macOS
# ships. Whether 3.9 is genuinely good enough is decided empirically by the smoke
# test below, not by trusting a version number here.
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
if ! PY_BIN="$(find_python)"; then
  echo
  echo "  No Python 3.9 or newer found, which is surprising on a modern Mac."
  echo "  Install one, then run this script again:"
  echo
  echo "      brew install python@3.12"
  echo
  echo "  (If you don't have Homebrew: https://brew.sh)"
  exit 1
fi
say "Using $PY_BIN ($("$PY_BIN" --version))"

# --- 2. Virtualenv ------------------------------------------------------------
# Required, not optional: Homebrew and recent macOS Pythons are marked
# externally-managed (PEP 668) and refuse a plain `pip install`.
say "Creating virtualenv at .venv"
"$PY_BIN" -m venv "$REPO/.venv"
"$REPO/.venv/bin/python" -m pip install --quiet --upgrade pip
"$REPO/.venv/bin/python" -m pip install --quiet -r "$REPO/requirements.txt"
shasum -a 256 "$REPO/requirements.txt" | cut -d' ' -f1 > "$REPO/.venv/.requirements.sha"
say "Dependencies installed"

# Playwright drives the application forms. The chromium download is ~150 MB
# once; skipped silently if already present.
say "Installing the form-filling browser (one-time, ~150 MB)"
"$REPO/.venv/bin/python" -m playwright install chromium >/dev/null 2>&1   || warn "browser install failed - applications will queue as apply-by-hand"

chmod +x "$REPO/scripts/run_harvest.sh" "$REPO/scripts/uninstall_mac.sh" 2>/dev/null || true

# --- 2b. Prove this interpreter actually works --------------------------------
# Exercises one real path through every module. Catches a version incompatibility
# now, at a keyboard, instead of silently at 3am in an unattended run.
say "Checking this Python can run Meester"
if ! "$REPO/.venv/bin/python" "$REPO/scripts/smoke_test.py"; then
  echo
  echo "  This Python cannot run Meester correctly."
  echo "  Install a newer one and run this script again:"
  echo
  echo "      brew install python@3.12"
  echo
  echo "  (If you don't have Homebrew: https://brew.sh)"
  exit 1
fi

# --- 3. Verify board tokens ---------------------------------------------------
say "Verifying job board tokens (takes a minute)"
"$REPO/.venv/bin/python" -m meester verify-companies --write || \
  warn "verification had problems - harvest will fall back to the unverified list"

# --- 4. Schedule via launchd --------------------------------------------------
# launchd, not cron: if the machine is asleep when a job is due, cron drops it
# silently whereas launchd runs it once on wake. On a laptop that is the whole
# ballgame.
say "Installing scheduled job (every ${INTERVAL}s)"
mkdir -p "$HOME/Library/LaunchAgents" "$REPO/logs"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>$REPO/scripts/run_harvest.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$REPO</string>

    <key>StartInterval</key>
    <integer>$INTERVAL</integer>

    <!-- Run once at login so a freshly-opened laptop catches up immediately. -->
    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$REPO/logs/launchd.out.log</string>
    <key>StandardErrorPath</key>
    <string>$REPO/logs/launchd.err.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <!-- Never let a background job make the machine feel slow. -->
    <key>ProcessType</key>
    <string>Background</string>
    <key>LowPriorityIO</key>
    <true/>
    <key>Nice</key>
    <integer>5</integer>
</dict>
</plist>
PLIST_EOF

# Replace any previous copy. bootout on a job that isn't loaded returns non-zero,
# which is fine and expected on a first install.
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if ! launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null; then
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST" || die "could not register the scheduled job"
fi

say "Scheduled job installed"

# --- 4b. Local UI service -----------------------------------------------------
# A page opened as file:// cannot write to disk, and Safari has no File System
# Access API, so editing the watchlist without a terminal needs a local server.
# Bound to 127.0.0.1 only. KeepAlive restarts it if it ever dies.
UI_LABEL="com.meester.ui"
UI_PLIST="$HOME/Library/LaunchAgents/$UI_LABEL.plist"
UI_PORT="${MEESTER_PORT:-8765}"

say "Installing the Companies screen (localhost:$UI_PORT)"
cat > "$UI_PLIST" <<UI_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$UI_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$REPO/.venv/bin/python</string>
        <string>-m</string>
        <string>meester</string>
        <string>serve</string>
        <string>--port</string>
        <string>$UI_PORT</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$REPO</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$REPO/logs/ui.out.log</string>
    <key>StandardErrorPath</key>
    <string>$REPO/logs/ui.err.log</string>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
UI_EOF

launchctl bootout "gui/$(id -u)/$UI_LABEL" 2>/dev/null || true
if ! launchctl bootstrap "gui/$(id -u)" "$UI_PLIST" 2>/dev/null; then
  launchctl unload "$UI_PLIST" 2>/dev/null || true
  launchctl load "$UI_PLIST" 2>/dev/null || warn "could not start the Companies screen"
fi

# --- 5. Desktop shortcut ------------------------------------------------------
# The whole system is worthless to her if reaching the results needs a terminal.
# A symlink resolves once the first harvest writes the file, which the RunAtLoad
# above triggers immediately.
ALIAS="$HOME/Desktop/Remote jobs.html"
if ln -sfn "$REPO/data/jobs.html" "$ALIAS" 2>/dev/null; then
  say "Added 'Remote jobs' to her Desktop"
else
  warn "could not create the Desktop shortcut - she can open $REPO/data/jobs.html directly"
fi

cat <<EOF

  Setup complete.

  It runs every $((INTERVAL / 60)) minutes, and once whenever she logs in.

  She opens:                the "Remote jobs" file on her Desktop

  Check it is running:      launchctl list | grep meester
  Watch the log:            tail -f "$REPO/logs/harvest.log"
  See what it found:        "$REPO/.venv/bin/python" -m meester show --limit 40
  Pause everything:         touch "$REPO/PAUSED"
  Resume:                   rm "$REPO/PAUSED"
  Remove completely:        "$REPO/scripts/uninstall_mac.sh"

  About sleep: a closed MacBook Air suspends the timer. launchd will fire one
  catch-up run on wake, so in practice this harvests whenever the laptop is
  awake rather than strictly hourly. To narrow the gap, keep it on the charger
  and enable System Settings > Battery > Options > "Wake for network access".

EOF
