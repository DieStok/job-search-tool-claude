# =============================================================================
# linkedin-coffee-pipeline — Windows Task Scheduler daily job registration
# =============================================================================
# This is the Windows equivalent of scripts/schedule_macos.sh, which registers
# a macOS launchd LaunchAgent. This script registers a Windows Scheduled Task
# that runs scripts\run_daily.ps1 once per day at a configurable local time
# (default 08:30, matching scripts/schedule_macos.sh). Decoupled from Claude
# Desktop: the scrape runs
# even when the app is closed.
#
# Usage:
#   scripts\schedule_windows.ps1                       # register/update the task
#   scripts\schedule_windows.ps1 -Unregister           # remove the scheduled task
#   scripts\schedule_windows.ps1 -DryRun               # print actions, change nothing
#   scripts\schedule_windows.ps1 -Hour 8 -Minute 30    # custom time (08:30)
#
# Idempotent: unregisters any existing task of the same name then re-registers.
#
# Requirements:
#   Windows 8+ / Server 2012+ (ScheduledTasks module, included in PS 5.1+).
#   Runs as the current user ("Run only when user is logged on").
#   No elevation required for current-user tasks; run as Administrator to
#   register as SYSTEM or for all users.
#
# Task Scheduler equivalent of macOS launchd plist:
#   ~/Library/LaunchAgents/com.linkedin-coffee-pipeline.daily.plist
#
# Linux/other: use cron instead — see the CRON note printed at the end, or
#   refer to scripts/schedule_macos.sh for the launchd approach.
# =============================================================================

param(
    [switch]$Unregister,
    [switch]$DryRun,
    [int]$Hour   = 8,
    [int]$Minute = 30
)

$ErrorActionPreference = 'Stop'

$taskName = "linkedin-coffee-pipeline"
$repo     = Split-Path -Parent $PSScriptRoot
$runner   = Join-Path $repo "scripts\run_daily.ps1"
$timeStr  = "{0:D2}:{1:D2}" -f $Hour, $Minute

# ASCII markers only (PS 5.1 mojibakes Unicode glyphs in BOM-less .ps1 files).
function Say  { param([string]$msg) Write-Host ">> $msg" -ForegroundColor Cyan }
function Ok   { param([string]$msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Warn { param([string]$msg) Write-Host "[!] $msg" -ForegroundColor Yellow }
function Die  { param([string]$msg) Write-Host "[X] $msg" -ForegroundColor Red; exit 1 }

# --- unregister ---------------------------------------------------------------
if ($Unregister) {
    Say "Removing scheduled task '$taskName'"
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        if ($DryRun) {
            Write-Host "   [dry-run] Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false"
        } else {
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
            Ok "Removed task '$taskName'"
        }
    } else {
        Warn "Task '$taskName' not found — nothing to remove"
    }
    exit 0
}

# --- register -----------------------------------------------------------------
Say "Registering daily scheduled task '$taskName' at $timeStr local"

if (-not (Test-Path $runner)) {
    Die "Runner script not found: $runner"
}

$action = New-ScheduledTaskAction `
    -Execute        "powershell.exe" `
    -Argument       "-NoProfile -ExecutionPolicy Bypass -File `"$runner`"" `
    -WorkingDirectory $repo

$triggerTime = Get-Date -Hour $Hour -Minute $Minute -Second 0
$trigger     = New-ScheduledTaskTrigger -Daily -At $triggerTime

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances  IgnoreNew `
    -StartWhenAvailable

if ($DryRun) {
    Write-Host "   [dry-run] Would register task '$taskName':"
    Write-Host "     Execute:          powershell.exe"
    Write-Host "     Arguments:        -NoProfile -ExecutionPolicy Bypass -File `"$runner`""
    Write-Host "     Working dir:      $repo"
    Write-Host "     Schedule:         Daily at $timeStr"
    Write-Host "     MultipleInstances: IgnoreNew"
    Write-Host "     StartWhenAvailable: yes (catches missed runs)"
    Write-Host "   [dry-run] Idempotent: would unregister existing task first if present"
    exit 0
}

# Unregister first for idempotency (unregister-then-register pattern)
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Warn "Replaced existing task '$taskName'"
}

# Ensure data/runs dir exists for log output written by run_daily.ps1
$runsDir = Join-Path $repo "data\runs"
if (-not (Test-Path $runsDir)) {
    New-Item -ItemType Directory -Force -Path $runsDir | Out-Null
}

Register-ScheduledTask `
    -TaskName   $taskName `
    -Action     $action `
    -Trigger    $trigger `
    -Settings   $settings `
    -Description "linkedin-coffee-pipeline daily core: proxy check, jobs fetch, jobs rank" | Out-Null

Ok "Scheduled daily at $timeStr local — task '$taskName'"
Write-Host ""
Write-Host "To view/edit the task: open Task Scheduler (taskschd.msc) and look for '$taskName'"
Write-Host "To remove:             .\scripts\schedule_windows.ps1 -Unregister"
Write-Host ""
Write-Host "CRON note (Linux / non-Windows): add to crontab -e:"
Write-Host "  $Minute $Hour * * *  cd `"$repo`" && scripts/run_daily.sh"
