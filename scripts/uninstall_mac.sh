#!/usr/bin/env bash
# Stop and remove the scheduled job. Leaves the code and the collected data
# alone - this only unschedules it.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.meester.harvest"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

UI_LABEL="com.meester.ui"
UI_PLIST="$HOME/Library/LaunchAgents/$UI_LABEL.plist"

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
