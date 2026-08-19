#!/usr/bin/env bash
# Stop and remove the scheduled job. Leaves the code and the collected data
# alone - this only unschedules it.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.meester.harvest"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

UI_LABEL="com.meester.ui"
UI_PLIST="$HOME/Library/LaunchAgents/$UI_LABEL.plist"

# Same hazard as setup_mac.sh, in reverse: the labels are fixed but REPO is not,
# so running this from a dev clone would unschedule her real, running job search
# from an entirely different folder - and print a cheerful success message while
# doing it.
if [[ -f "$PLIST" ]] && ! grep -q "<string>$REPO/scripts/run_harvest.sh</string>" "$PLIST" 2>/dev/null; then
  if [[ -z "${MEESTER_FORCE:-}" ]]; then
    printf 'error: the scheduled job runs from another folder, not this one:
' >&2
    printf '    %s

' "$REPO" >&2
    printf '  Uninstalling from here would stop her live job search. Nothing changed.
' >&2
    printf '  If you really mean it:  MEESTER_FORCE=1 %s
' "$0" >&2
    exit 1
  fi
fi

for pair in "$LABEL|$PLIST" "$UI_LABEL|$UI_PLIST"; do
  label="${pair%%|*}"; plist="${pair##*|}"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null \
    || launchctl unload "$plist" 2>/dev/null || true
  rm -f "$plist"
done

rm -f "$HOME/Desktop/Remote jobs.html"

echo "Scheduled job and Companies screen removed. Nothing runs automatically any more."
echo
echo "Your data is untouched at: $REPO/data"
echo "To delete it as well:      rm -rf \"$REPO/data\" \"$REPO/logs\""
