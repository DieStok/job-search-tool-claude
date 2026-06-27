#!/usr/bin/env bash
# =============================================================================
# linkedin-coffee-pipeline — one-command installer (friendly for non-git users)
# =============================================================================
# Usage:
#   ./install.sh                 # full install: deps + config + show next steps
#   ./install.sh --dry-run       # print what it WOULD do, change nothing
#   ./install.sh claude-desktop  # (re)wire the MCP server into Claude Desktop
#   ./install.sh check           # health check only
#
# Idempotent: safe to run again. NEVER overwrites an existing config you edited.
# macOS-first (you're on a Mac); Linux notes inline. No GitHub knowledge needed.
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

DRY=0
CMD="install"
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    claude-desktop) CMD="claude-desktop" ;;
    check) CMD="check" ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
  esac
done

say()  { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then printf '   [dry-run] %s\n' "$*"; else eval "$*"; fi; }

# --- locate a python + uv -----------------------------------------------------
ensure_tools() {
  if command -v uv >/dev/null 2>&1; then
    ok "uv found ($(uv --version 2>/dev/null))"
  else
    warn "uv not found — installing it (fast Python package manager)"
    if [ "$DRY" = 1 ]; then
      printf '   [dry-run] curl -LsSf https://astral.sh/uv/install.sh | sh\n'
    else
      curl -LsSf https://astral.sh/uv/install.sh | sh || die "uv install failed — see https://docs.astral.sh/uv/"
      export PATH="$HOME/.local/bin:$PATH"
    fi
  fi
}

# --- venv + deps --------------------------------------------------------------
install_deps() {
  say "Creating virtual environment (.venv) and installing the pipeline"
  run "uv venv .venv"
  # 'all' brings the scrapers (JobSpy/StaffSpy) + MCP server; dev adds test tooling.
  run "uv pip install --python .venv/bin/python -e '.[all,dev]'"
  ok "dependencies installed"
}

# --- config (copy examples, never clobber) ------------------------------------
install_config() {
  say "Setting up your config (won't touch files you've already edited)"
  for f in config.yaml profile.yaml rubric.yaml; do
    if [ -f "config/$f" ]; then
      ok "config/$f already exists — left untouched"
    else
      run "cp 'config/${f%.yaml}.example.yaml' 'config/$f'"
      ok "created config/$f (edit it!)"
    fi
  done
  if [ ! -f .env ]; then
    run "cp .env.example .env"
    ok "created .env (put any API keys here; it's git-ignored)"
  else
    ok ".env already exists — left untouched"
  fi
  run "mkdir -p data data/runs"
}

# --- Claude Desktop MCP wiring ------------------------------------------------
wire_claude_desktop() {
  say "Wiring the pipeline MCP server into Claude Desktop"
  local py="$HERE/.venv/bin/python"
  [ -x "$py" ] || die "run ./install.sh first (no .venv yet)"
  if [ "$DRY" = 1 ]; then
    "$py" scripts/wire_claude_desktop.py --repo "$HERE" --print
  else
    "$py" scripts/wire_claude_desktop.py --repo "$HERE" \
      && ok "Claude Desktop config updated (backup saved). Restart Claude Desktop." \
      || warn "Could not auto-wire. Paste the JSON below into claude_desktop_config.json:"
    [ $? -ne 0 ] && "$py" scripts/wire_claude_desktop.py --repo "$HERE" --print || true
  fi
}

# --- health check -------------------------------------------------------------
health() {
  say "Health check"
  local py="$HERE/.venv/bin/python"
  if [ -x "$py" ]; then
    "$py" -m lcp.cli doctor || warn "doctor reported issues (see above)"
  else
    warn ".venv missing — run ./install.sh"
  fi
}

next_steps() {
  cat <<EOF

$(ok "Install complete.")
Next steps:
  1. Edit  config/profile.yaml   — who you are (for warmth matching)
  2. Edit  config/rubric.yaml    — the jobs you want + warmth weights
  3. Edit  config/config.yaml    — knobs (proxy, people layer, enrichment) — baselines already set
  4. Try it:   .venv/bin/lcp jobs fetch --dry-run   &&   .venv/bin/lcp doctor
  5. Wire Claude Desktop:   ./install.sh claude-desktop   (then restart Claude Desktop)
  6. Read    docs/CLAUDE_DESKTOP.md  and  docs/COMPLIANCE.md  (GDPR/NL — please read!)

The deterministic core runs without Claude. Claude Desktop adds the judgment layer.
EOF
}

case "$CMD" in
  install)        ensure_tools; install_deps; install_config; health; next_steps ;;
  claude-desktop) wire_claude_desktop ;;
  check)          health ;;
esac
