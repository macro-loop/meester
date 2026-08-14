#!/usr/bin/env bash
# Stop and remove the scheduled job. Leaves the code and the collected data
# alone - this only unschedules it.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.meester.harvest"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"

echo "Scheduled job removed. Nothing will run automatically any more."
echo
echo "Your data is untouched at: $REPO/data"
echo "To delete it as well:      rm -rf \"$REPO/data\" \"$REPO/logs\""
