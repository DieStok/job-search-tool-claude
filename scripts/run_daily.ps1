# The daily deterministic core run (called by Task Scheduler). JobSpy-only; no LinkedIn login.
# proxy check -> jobs fetch -> jobs rank. People/enrichment/outreach stay human-in-the-loop in Claude.

param(
    [switch]$DryRun
)

$ErrorActionPreference = 'Continue'

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$lcpExe = Join-Path $repo ".venv\Scripts\lcp.exe"
$lcpPy  = Join-Path $repo ".venv\Scripts\python.exe"

# Prefer the installed console script; fall back to python -m lcp.cli
if (Test-Path $lcpExe) {
    $lcpBin   = $lcpExe
    $lcpIsExe = $true
} elseif (Test-Path $lcpPy) {
    $lcpBin   = $lcpPy
    $lcpIsExe = $false
} else {
    Write-Error "no .venv — run .\install.ps1 first"
    exit 1
}

function ts { Get-Date -Format "yyyy-MM-ddTHH:mm:ss" }

$logDir  = Join-Path $repo "data\runs"
$logDate = Get-Date -Format "yyyy-MM-dd"
$logFile = Join-Path $logDir "daily-$logDate.log"

# In -DryRun we change nothing on disk: skip creating the log dir / writing the log.
if (-not $DryRun -and -not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}

function Log {
    param([string]$msg)
    $line = "[$(ts)] $msg"
    Write-Host $line
    if (-not $script:DryRun) {
        Add-Content -Path $script:logFile -Value $line
    }
}

function Invoke-Lcp {
    param([string[]]$lcpArgs)
    if ($script:DryRun) {
        Write-Host "   [dry-run] lcp $($lcpArgs -join ' ')"
        return
    }
    if ($script:lcpIsExe) {
        & $script:lcpBin @lcpArgs
    } else {
        $fullArgs = @('-m', 'lcp.cli') + $lcpArgs
        & $script:lcpBin @fullArgs
    }
    if ($LASTEXITCODE -ne 0) {
        Log "$($lcpArgs -join ' ') failed (continuing)"
    }
}

Log "daily core start"
Invoke-Lcp @('proxies', 'check')
Invoke-Lcp @('jobs', 'fetch')
Invoke-Lcp @('jobs', 'rank')
Log "daily core done"
