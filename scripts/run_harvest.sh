#!/usr/bin/env bash
# Wrapper that launchd calls. Everything it needs is derived from its own
# location, so the repo can live anywhere and be moved without reconfiguring.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

LOG_DIR="$REPO/logs"
LOG="$LOG_DIR/harvest.log"
mkdir -p "$LOG_DIR"

# Always append to the log; additionally echo to the terminal when a person is
# watching. launchd runs this with stdout pointed at a file nobody reads, so
# without the TTY check a manual run looks like it did nothing at all.
log() {
  local line
  line="$(date '+%Y-%m-%d %H:%M:%S')  $*"
  printf '%s\n' "$line" >> "$LOG"
  if [[ -t 1 ]]; then printf '%s\n' "$line"; fi
}

interactive() { [[ -t 1 ]]; }

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
      if [[ "$before" != "$after" ]]; then
        log "updated ${before:0:7} -> ${after:0:7}"
        # bash keeps reading the copy of this file it opened at startup, so a
        # change to THIS script would otherwise not take effect until the *next*
        # run. That makes a pushed fix look like it did nothing, on a machine
        # nobody is watching. Re-exec once if this script itself changed;
        # MEESTER_REEXEC guards against looping.
        if [[ -z "${MEESTER_REEXEC:-}" ]] &&
           ! git -C "$REPO" diff --quiet "$before" "$after" -- scripts/run_harvest.sh 2>/dev/null; then
          log "run_harvest.sh itself changed - restarting on the new version"
          export MEESTER_REEXEC=1
          exec /bin/bash "$REPO/scripts/run_harvest.sh"
        fi
      fi
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

# --- company watchlist --------------------------------------------------------
# harvest reads companies.verified.yaml, which is gitignored and generated
# locally. Without this block, adding companies to companies.yaml and pushing
# would have no effect here at all - the highest-leverage maintenance task in
# the system would silently do nothing.
#
# Re-verify when the tracked seed list changes, or weekly to catch boards that
# have since died.
VERIFIED="$REPO/config/companies.verified.yaml"
SEED_STAMP="$VENV/.companies.sha"
SEED_NOW="$(shasum -a 256 "$REPO/config/companies.yaml" | cut -d' ' -f1)"
NEEDS_VERIFY=0

if [[ ! -f "$VERIFIED" ]]; then
  NEEDS_VERIFY=1; VERIFY_WHY="no verified list yet"
elif [[ ! -f "$SEED_STAMP" ]] || [[ "$(cat "$SEED_STAMP")" != "$SEED_NOW" ]]; then
  NEEDS_VERIFY=1; VERIFY_WHY="companies.yaml changed"
elif [[ -n "$(find "$VERIFIED" -mtime +7 2>/dev/null)" ]]; then
  NEEDS_VERIFY=1; VERIFY_WHY="verified list older than 7 days"
fi

if [[ $NEEDS_VERIFY -eq 1 ]]; then
  log "re-verifying board tokens ($VERIFY_WHY)"
  if "$PY" -m meester verify-companies --write >>"$LOG" 2>&1; then
    echo "$SEED_NOW" > "$SEED_STAMP"
    log "board tokens re-verified"
  else
    log "WARNING: token verification failed - continuing with existing list"
  fi
fi

# --- run ----------------------------------------------------------------------
# Record which commit produced this run, so a version can be confirmed remotely
# from the log alone.
if [[ -d "$REPO/.git" ]]; then
  log "harvest starting (code $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown))"
else
  log "harvest starting"
fi
OUT="$("$PY" -m meester harvest --limit 0 2>&1)"
RC=$?
printf '%s\n' "$OUT" | sed 's/^/    /' >> "$LOG"
if interactive; then printf '%s\n' "$OUT" | sed 's/^/    /'; fi

if [[ $RC -ne 0 ]]; then
  log "harvest FAILED (exit $RC)"
else
  log "harvest ok"
fi

# --- desktop shortcut ---------------------------------------------------------
# Machines set up before the report existed would otherwise never get the alias,
# because setup_mac.sh only runs by hand. Guarded by a marker so that deleting
# the alias deliberately keeps it deleted rather than resurrecting it every hour.
ALIAS_MARK="$VENV/.desktop_alias_done"
if [[ ! -f "$ALIAS_MARK" ]] && [[ -d "$HOME/Desktop" ]] && [[ -f "$REPO/data/jobs.html" ]]; then
  if ln -sfn "$REPO/data/jobs.html" "$HOME/Desktop/Remote jobs.html" 2>/dev/null; then
    touch "$ALIAS_MARK"
    log "added 'Remote jobs' shortcut to the Desktop"
  fi
fi

if interactive; then
  printf '\nFull log: %s\n' "$LOG"
  printf 'Open the results: the "Remote jobs" file on the Desktop\n\n'
fi

# --- log rotation -------------------------------------------------------------
# Unattended jobs that log forever eventually fill a 256GB laptop.
if [[ -f "$LOG" ]] && [[ "$(wc -l < "$LOG")" -gt 5000 ]]; then
  tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  log "log trimmed"
fi

exit $RC
