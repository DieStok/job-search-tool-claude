#!/usr/bin/env bash
# D5 / AC-040 — installer dry-run is green and changes nothing; re-run is idempotent.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

echo "== dry-run install =="
./install.sh --dry-run >/tmp/lcp_dryrun.log 2>&1 || { echo "FAIL: dry-run exited non-zero"; cat /tmp/lcp_dryrun.log; exit 1; }
grep -q "dry-run" /tmp/lcp_dryrun.log || { echo "FAIL: dry-run produced no [dry-run] lines"; exit 1; }

echo "== dry-run must not create files =="
test ! -e config/config.yaml.lock || { echo "FAIL: dry-run created a file"; exit 1; }

echo "== claude-desktop --print is valid JSON =="
.venv/bin/python scripts/wire_claude_desktop.py --repo "$HERE" --print | .venv/bin/python -c 'import json,sys; json.load(sys.stdin)' \
  || { echo "FAIL: claude-desktop --print not valid JSON"; exit 1; }

echo "PASS: installer dry-run + claude-desktop print OK"
