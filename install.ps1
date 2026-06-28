# =============================================================================
# linkedin-coffee-pipeline — one-command installer for Windows (PowerShell)
# =============================================================================
# Usage:
#   .\install.ps1                     # full install: deps + config + show next steps
#   .\install.ps1 -DryRun             # print what it WOULD do, change nothing
#   .\install.ps1 claude-desktop      # (re)wire the MCP server into Claude Desktop
#   .\install.ps1 claude-code         # confirm Claude Code .mcp.json is present
#   .\install.ps1 check               # health check only
#   .\install.ps1 -Help               # show this help
#
# Idempotent: safe to run again. NEVER overwrites an existing config you edited.
# Compatible with Windows PowerShell 5.1 and PowerShell 7+.
# No GitHub knowledge needed.
# =============================================================================

param(
    [Parameter(Position = 0)]
    [string]$Command = 'install',

    [switch]$DryRun,

    [Alias('h')]
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

$HERE = $PSScriptRoot
Set-Location $HERE

if ($Help) {
    Write-Host @"
linkedin-coffee-pipeline — Windows installer

Usage:
  .\install.ps1                     # full install: deps + config + show next steps
  .\install.ps1 -DryRun             # print what it WOULD do, change nothing
  .\install.ps1 claude-desktop      # (re)wire the MCP server into Claude Desktop
  .\install.ps1 claude-code         # confirm Claude Code .mcp.json is present
  .\install.ps1 check               # health check only
  .\install.ps1 -Help               # show this help

Idempotent: safe to run again. NEVER overwrites an existing config you edited.
"@
    exit 0
}

# --- colored output helpers ---------------------------------------------------
# ASCII markers only — Windows PowerShell 5.1 reads BOM-less .ps1 as the ANSI
# codepage, which turns Unicode glyphs into mojibake. ASCII renders everywhere.
function Say  { param([string]$msg) Write-Host ">> $msg" -ForegroundColor Cyan }
function Ok   { param([string]$msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn { param([string]$msg) Write-Host "[!] $msg" -ForegroundColor Yellow }
function Die  {
    param([string]$msg)
    Write-Host "[X] $msg" -ForegroundColor Red
    exit 1
}

# --- locate uv ----------------------------------------------------------------
function Ensure-Tools {
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($uvCmd) {
        $uvVer = & uv --version 2>$null
        Ok "uv found ($uvVer)"
    } else {
        Warn "uv not found — installing it (fast Python package manager)"
        if ($DryRun) {
            Write-Host "   [dry-run] Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression"
        } else {
            Invoke-RestMethod 'https://astral.sh/uv/install.ps1' | Invoke-Expression
            $uvLocalBin = Join-Path $env:USERPROFILE ".local\bin"
            if ($env:PATH -notlike "*$uvLocalBin*") {
                $env:PATH = "$uvLocalBin;$env:PATH"
            }
            # Re-validate: if uv still isn't resolvable, fail loudly rather than
            # crashing later inside Install-Deps with a confusing error.
            if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
                Die "uv installed but not on PATH — open a new terminal and re-run .\install.ps1 (see https://docs.astral.sh/uv/)"
            }
            Ok "uv installed"
        }
    }
}

# --- venv + deps --------------------------------------------------------------
function Install-Deps {
    Say "Creating virtual environment (.venv) and installing the pipeline"
    $pyPath = Join-Path $HERE ".venv\Scripts\python.exe"
    if ($DryRun) {
        Write-Host "   [dry-run] uv venv .venv"
        Write-Host "   [dry-run] uv pip install --python $pyPath -e '.[all,dev]'"
    } else {
        & uv venv .venv
        if ($LASTEXITCODE -ne 0) { Die "uv venv failed" }
        # 'all' brings the scrapers (JobSpy/StaffSpy) + MCP server; dev adds test tooling.
        & uv pip install --python $pyPath -e ".[all,dev]"
        if ($LASTEXITCODE -ne 0) { Die "uv pip install failed" }
        Ok "dependencies installed"
    }
}

# --- config (copy examples, never clobber) ------------------------------------
function Install-Config {
    Say "Setting up your config (won't touch files you've already edited)"
    foreach ($f in @('config.yaml', 'profile.yaml', 'rubric.yaml')) {
        $dest = Join-Path $HERE "config\$f"
        $base = $f -replace '\.yaml$', ''
        $src  = Join-Path $HERE "config\$base.example.yaml"
        if (Test-Path $dest) {
            Ok "config\$f already exists — left untouched"
        } else {
            if ($DryRun) {
                Write-Host "   [dry-run] Copy-Item '$src' -> '$dest'"
            } else {
                Copy-Item $src $dest
                Ok "created config\$f (edit it!)"
            }
        }
    }
    $envDest = Join-Path $HERE ".env"
    $envSrc  = Join-Path $HERE ".env.example"
    if (-not (Test-Path $envDest)) {
        if ($DryRun) {
            Write-Host "   [dry-run] Copy-Item '$envSrc' -> '$envDest'"
        } else {
            Copy-Item $envSrc $envDest
            Ok "created .env (put any API keys here; it's git-ignored)"
        }
    } else {
        Ok ".env already exists — left untouched"
    }
    $runsDir = Join-Path $HERE "data\runs"
    if (-not (Test-Path $runsDir)) {
        if ($DryRun) {
            Write-Host "   [dry-run] New-Item -ItemType Directory -Force '$runsDir'"
        } else {
            New-Item -ItemType Directory -Force -Path $runsDir | Out-Null
        }
    }
}

# --- Claude Desktop MCP wiring ------------------------------------------------
function Wire-ClaudeDesktop {
    Say "Wiring the pipeline MCP server into Claude Desktop"
    $py = Join-Path $HERE ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        Die "run .\install.ps1 first (no .venv yet)"
    }
    $wireScript = Join-Path $HERE "scripts\wire_claude_desktop.py"
    if ($DryRun) {
        & $py $wireScript --repo $HERE --print
    } else {
        & $py $wireScript --repo $HERE
        if ($LASTEXITCODE -ne 0) {
            Warn "Could not auto-wire. Paste the JSON below into claude_desktop_config.json:"
            & $py $wireScript --repo $HERE --print
        } else {
            Ok "Claude Desktop config updated (backup saved). Restart Claude Desktop."
        }
    }
}

# --- Claude Code integration --------------------------------------------------
function Wire-ClaudeCode {
    Say "Claude Code integration"
    $mcpJson = Join-Path $HERE ".mcp.json"
    if (Test-Path $mcpJson) {
        Ok "Project '.mcp.json' is present — Claude Code auto-detects it."
        Write-Host "   Open this folder in Claude Code and approve the 'linkedin-coffee-pipeline' MCP server"
        Write-Host "   when prompted (Claude Code lists project MCP servers on first use)."
        Write-Host "   The server runs via 'uv run' (portable — no venv activation required)."
    } else {
        Warn ".mcp.json missing — re-pull the repo (it ships at the project root)."
    }
}

# --- health check -------------------------------------------------------------
function Health {
    Say "Health check"
    $py = Join-Path $HERE ".venv\Scripts\python.exe"
    if (Test-Path $py) {
        & $py -m lcp.cli doctor
        if ($LASTEXITCODE -ne 0) {
            Warn "doctor reported issues (see above)"
        }
    } else {
        Warn ".venv missing — run .\install.ps1"
    }
}

function Next-Steps {
    Write-Host ""
    Ok "Install complete."
    Write-Host "Next steps:"
    Write-Host "  1. Edit  config\profile.yaml   — who you are (for warmth matching)"
    Write-Host "  2. Edit  config\rubric.yaml    — the jobs you want + warmth weights"
    Write-Host "  3. Edit  config\config.yaml    — knobs (proxy, people layer, enrichment) — baselines already set"
    Write-Host "  4. Try:  .venv\Scripts\lcp.exe jobs fetch --dry-run"
    Write-Host "           .venv\Scripts\lcp.exe doctor"
    Write-Host "  5a. Claude Desktop:  .\install.ps1 claude-desktop  (merges MCP server, then restart it)"
    Write-Host "  5b. Claude Code:     .\install.ps1 claude-code     (uses project .mcp.json — approve on first use)"
    Write-Host "  6. Read  docs\CLAUDE_DESKTOP.md  and  docs\COMPLIANCE.md  (GDPR/NL — please read!)"
    Write-Host ""
    Write-Host "The deterministic core runs without Claude. Claude Code / Claude Desktop add the judgment layer."
}

# --- dispatch -----------------------------------------------------------------
switch ($Command) {
    'install' {
        Ensure-Tools
        Install-Deps
        Install-Config
        Health
        Next-Steps
    }
    'claude-desktop' { Wire-ClaudeDesktop }
    'claude-code'    { Wire-ClaudeCode }
    'check'          { Health }
    default          { Die "Unknown command '$Command'. Use: install, claude-desktop, claude-code, check" }
}
