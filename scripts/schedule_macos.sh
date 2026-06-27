#!/usr/bin/env bash
# D5 / AC-043 — schedule the deterministic core (proxy check → jobs fetch → jobs rank)
# via macOS launchd. Decoupled from Claude Desktop (the scrape runs even if the app is closed).
#
# Usage:
#   scripts/schedule_macos.sh install     # install + load the daily LaunchAgent
#   scripts/schedule_macos.sh uninstall   # unload + remove it
#   scripts/schedule_macos.sh --dry-run   # print the plist + actions, change nothing
#
# Linux/other: use cron instead — see the CRON note printed at the end.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.linkedin-coffee-pipeline.daily"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
HOUR=8; MIN=30   # 08:30 local — inside the safe automation window

DRY=0; CMD="${1:-install}"
[ "${1:-}" = "--dry-run" ] && { DRY=1; CMD="install"; }

RUNNER="$HERE/scripts/run_daily.sh"

gen_plist() {
  cat <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$RUNNER</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MIN</integer></dict>
  <key>WorkingDirectory</key><string>$HERE</string>
  <key>StandardOutPath</key><string>$HERE/data/runs/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$HERE/data/runs/launchd.err.log</string>
  <key>RunAtLoad</key><false/>
</dict>
</plist>
EOF
}

case "$CMD" in
  install)
    if [ "$DRY" = 1 ]; then
      echo "[dry-run] would write $PLIST :"; gen_plist
      echo "[dry-run] would: launchctl unload/load $PLIST"
      exit 0
    fi
    mkdir -p "$HOME/Library/LaunchAgents" "$HERE/data/runs"
    gen_plist > "$PLIST"
    plutil -lint "$PLIST" >/dev/null || { echo "FAIL: generated plist invalid"; exit 1; }
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "✓ scheduled daily at $(printf '%02d:%02d' $HOUR $MIN) local — $LABEL"
    ;;
  uninstall)
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "✓ removed $LABEL"
    ;;
  *) echo "usage: $0 [install|uninstall|--dry-run]"; exit 2 ;;
esac

cat <<'CRON'

CRON note (Linux / non-macOS): add to `crontab -e`:
  30 8 * * *  cd /path/to/linkedin-coffee-pipeline && scripts/run_daily.sh
CRON
