#!/usr/bin/env bash
# The daily deterministic core run (called by launchd/cron). JobSpy-only; no LinkedIn login.
# proxy check → jobs fetch → jobs rank. People/enrichment/outreach stay human-in-the-loop in Claude.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"
LCP="$HERE/.venv/bin/lcp"
[ -x "$LCP" ] || { echo "no .venv — run ./install.sh first" >&2; exit 1; }

ts() { date "+%Y-%m-%dT%H:%M:%S"; }
echo "[$(ts)] daily core start"
"$LCP" proxies check || echo "[$(ts)] proxies check failed (continuing)"
"$LCP" jobs fetch     || echo "[$(ts)] jobs fetch failed (continuing)"
"$LCP" jobs rank      || echo "[$(ts)] jobs rank failed (continuing)"
echo "[$(ts)] daily core done"
