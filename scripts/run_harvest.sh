#!/usr/bin/env bash
# Wrapper that launchd calls. Everything it needs is derived from its own
# location, so the repo can live anywhere and be moved without reconfiguring.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

LOG_DIR="$REPO/logs"
LOG="$LOG_DIR/harvest.log"
mkdir -p "$LOG_DIR"

log() { printf '%s  %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

# --- pause switch -------------------------------------------------------------
# Creating an empty file named PAUSED in the project folder stops everything.
# Deliberately a file and not a config flag: it can be made or deleted from
# Finder by someone who has never opened a terminal.
if [[ -f "$REPO/PAUSED" ]]; then
  log "PAUSED file present - skipping run"
  exit 0
fi

# --- self-update --------------------------------------------------------------
# --ff-only so a local edit can never be clobbered; a diverged repo just logs
# and carries on with the code it already has rather than failing the run.
if [[ "${MEESTER_AUTO_UPDATE:-1}" == "1" ]] && [[ -d "$REPO/.git" ]]; then
  if git -C "$REPO" remote get-url origin >/dev/null 2>&1; then
    before="$(git -C "$REPO" rev-parse HEAD 2>/dev/null)"
    if git -C "$REPO" pull --ff-only --quiet 2>>"$LOG"; then
      after="$(git -C "$REPO" rev-parse HEAD 2>/dev/null)"
      [[ "$before" != "$after" ]] && log "updated ${before:0:7} -> ${after:0:7}"
    else
      log "git pull failed or diverged - continuing on current code"
    fi
  fi
fi

# --- dependencies -------------------------------------------------------------
VENV="$REPO/.venv"
PY="$VENV/bin/python"
if [[ ! -x "$PY" ]]; then
  log "ERROR: no virtualenv at $VENV - run scripts/setup_mac.sh"
  exit 1
fi

# Reinstall only when requirements.txt actually changed since the last install.
REQ_STAMP="$VENV/.requirements.sha"
REQ_NOW="$(shasum -a 256 "$REPO/requirements.txt" | cut -d' ' -f1)"
if [[ ! -f "$REQ_STAMP" ]] || [[ "$(cat "$REQ_STAMP")" != "$REQ_NOW" ]]; then
  log "requirements changed - installing"
  "$PY" -m pip install --quiet --upgrade -r "$REPO/requirements.txt" >>"$LOG" 2>&1 \
    && echo "$REQ_NOW" > "$REQ_STAMP" \
    || log "WARNING: dependency install failed"
fi

# --- run ----------------------------------------------------------------------
log "harvest starting"
OUT="$("$PY" -m meester harvest --limit 0 2>&1)"
RC=$?
printf '%s\n' "$OUT" | sed 's/^/    /' >> "$LOG"
if [[ $RC -ne 0 ]]; then
  log "harvest FAILED (exit $RC)"
else
  log "harvest ok"
fi

# --- log rotation -------------------------------------------------------------
# Unattended jobs that log forever eventually fill a 256GB laptop.
if [[ -f "$LOG" ]] && [[ "$(wc -l < "$LOG")" -gt 5000 ]]; then
  tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  log "log trimmed"
fi

exit $RC
