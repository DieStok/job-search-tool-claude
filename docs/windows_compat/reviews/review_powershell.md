VERDICT: APPROVE-WITH-NITS

Review covers deliverable D1 (install.ps1, run_daily.ps1, schedule_windows.ps1).

## Resolution (folded by orchestrator, 2026-06-28)
All actionable findings RESOLVED — no unresolved blocking finding remains:
- MAJOR (Unicode-glyph mojibake on PS 5.1): FIXED — all three .ps1 use ASCII markers
  (`>>`/`[OK]`/`[!]`/`[X]`); verified pure-ASCII via byte scan.
- MINOR m-1 (run_daily.ps1 wrote log in -DryRun): FIXED — log dir + Add-Content now guarded on -DryRun.
- MINOR m-2 (schedule default 09:00 vs mac 08:30): FIXED — default is now 08:30 for parity.
- MINOR m-3 (uv not re-validated after bootstrap): FIXED — install.ps1 re-checks `Get-Command uv` and dies clearly.
- MINOR m-4 (task has no stdout capture): ACCEPTED — run_daily.ps1 self-logs to data\runs\daily-*.log.
- NITs: not blocking; left as-is or covered by the above.
The PowerShell scripts are parsed on a real windows-latest CI runner (cross-platform.yml) as the live proof.

---

Reviewer: fresh-context checker (did not write the scripts)
Date: 2026-06-28
Scope: install.ps1, scripts/run_daily.ps1, scripts/schedule_windows.ps1
Reference AC: AC-001, AC-002, AC-007 (GOAL.md)
Cannot run pwsh (darwin host) — static analysis only.

---

## Findings

### BLOCKER (0)

None. All three files parse as valid PowerShell 5.1. No PS7-only constructs were found.
AC-001 verification (`[ScriptBlock]::Create(...)`) will exit 0 on a Windows runner.

---

### MAJOR (1)

**M-1 — Unicode glyphs without UTF-8 BOM guarantee cause mojibake on PS 5.1**
Files: install.ps1:50-56, schedule_windows.ps1:45-48
Problem:
Both files embed three non-ASCII Unicode characters in string literals:
  - U+25B8 `▸`  (UTF-8: E2 96 B8)
  - U+2713 `✓`  (UTF-8: E2 9C 93)
  - U+2717 `✗`  (UTF-8: E2 9C 97)

Windows PowerShell 5.1 reads `.ps1` files that lack a UTF-8 BOM using the system
ANSI codepage (CP1252 on most English Windows installations, or a regional variant
on enterprise boxes with a different locale). When the file is read under CP1252:

  - `✓` (E2 9C 93) → â + œ + U+201C (left typographic double-quote `"`)
    The U+201C that appears inside the string literal `"✓ $msg"` is NOT the ASCII
    delimiter (U+0022), so the parser does not break — but the string content is
    `âœ" $msg` (garbled). Every `Ok` call displays garbage.
  - `▸` (E2 96 B8) → â + U+2013 (en dash) + ¸  — renders as `â-¸`.
  - `✗` (E2 9C 97) → â + œ + U+2014 (em dash)  — renders as `âœ-`.

Every Write-Host progress/success/failure indicator is unreadable on a stock PS 5.1
session without explicit UTF-8 console setup. This affects both the interactive
installer experience and any CI log that captures the output.

Parsing does not fail (these mangled code points do not produce invalid PS tokens),
so the AC-001 `ScriptBlock::Create` parse test passes either way — the defect shows
up at runtime output, not parse time.

Severity: MAJOR (every user-visible status line is corrupted on default PS 5.1;
the AC says "PowerShell 5.1-compatible", which includes the runtime UX).

Concrete fix — two options:

Option A (preferred): Save all three `.ps1` files with UTF-8 BOM. The D4
`.gitattributes` deliverable that forces `eol=crlf` for `*.ps1` should also
enforce `encoding=utf-8-bom` (`.gitattributes` supports this via `working-tree-encoding`
or via an `.editorconfig` rule). BOM causes PS 5.1 to parse the file as UTF-8 and
also causes Windows Notepad / most editors to save with BOM by default.

Additionally, add this near the top of each `.ps1` script (before any Write-Host)
so the console renders the characters:

    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8

This covers the file-read side (BOM) and the console-render side (OutputEncoding).

Option B (no-BOM): Replace the three glyphs with ASCII-safe alternatives:
  - `▸`  ->  `>>`  or  `-->`
  - `✓`  ->  `[OK]`
  - `✗`  ->  `[X]`
  - `!` in Warn is already ASCII — no change needed.

Option B is simpler but loses the visual style parity with the bash script.

---

### MINOR (4)

**m-1 — run_daily.ps1 creates a log file in DryRun mode (side-effect violation)**
File: scripts/run_daily.ps1:34-36, 62, 66
Problem:
The script-level `Log` calls at lines 62 (`Log "daily core start"`) and 66
(`Log "daily core done"`) are invoked unconditionally, before and after the
`Invoke-Lcp` wrappers that honour `$DryRun`. `Log` calls `Add-Content` which
writes to `data\runs\daily-YYYY-MM-DD.log`. The `New-Item` directory creation at
lines 34-36 also executes unconditionally.

AC-007 says `-DryRun` must exit 0 on CI. It will — but a DryRun that writes to the
filesystem is surprising and could cause CI assertions that check for filesystem
side-effects to fail.

Fix: gate the `New-Item` block and the two bare `Log` calls on `(-not $DryRun)`,
or change `Log` to call `Write-Host` only when `$DryRun` is set instead of
`Add-Content`.

**m-2 — Default schedule time mismatch between Windows and macOS scripts**
Files: scripts/schedule_windows.ps1:35-36 vs scripts/schedule_macos.sh:15
Problem:
schedule_windows.ps1 defaults to `$Hour=9, $Minute=0` (09:00).
schedule_macos.sh defaults to `HOUR=8; MIN=30` (08:30).
A user who sets up both platforms will get different default run times with no
comment explaining the discrepancy. The GOAL.md D1 spec says "at parity with the
mac scripts."

Fix: align to 08:30 (`$Hour=8, $Minute=30`) or document the deliberate difference
in the script header comment.

**m-3 — uv not re-validated after Invoke-Expression install (Ensure-Tools)**
File: install.ps1:70-76
Problem:
After `Invoke-RestMethod '...' | Invoke-Expression` installs uv and PATH is
updated for `$env:PATH` in the current session, there is no subsequent
`Get-Command uv` re-check. If the uv installer exits 0 but the binary lands in a
different directory (e.g., a custom CARGO_HOME or a non-standard astral layout),
the downstream `& uv venv .venv` in `Install-Deps` will fail with a cryptic "uv is
not recognized" error rather than a helpful install-failure message.

Fix: after the `Invoke-Expression`, add:

    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCmd) { Die "uv install appeared to succeed but 'uv' is still not on PATH. Restart your shell and re-run." }

**m-4 — Scheduled Task has no stdout/stderr capture at the scheduler level**
File: scripts/schedule_windows.ps1:74-77
Problem:
The macOS equivalent (schedule_macos.sh) writes launchd keys
`StandardOutPath` and `StandardErrorPath` to the plist, so all output from
`run_daily.sh` is captured even if the script crashes before its own log
statements fire. The Windows Scheduled Task has no equivalent capture: the
`New-ScheduledTaskAction` is constructed with `powershell.exe ... run_daily.ps1`
and nothing redirects stdout/stderr at the scheduler level.

The `run_daily.ps1` internal logger (`Add-Content`) compensates for the happy path,
but any terminating error or exception that fires before `Log "daily core start"`
produces output that is visible only in Task Scheduler's event log (not in the
`data\runs` directory the user is told to inspect).

Fix: wrap the powershell.exe invocation to append stdout/stderr to the log file:

    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runner`" >> `"$logFile`" 2>&1"

Or note this limitation explicitly in the script header comment so operators know
to check Windows Event Log for crash output.

---

### NIT (4)

**n-1 — Private helper function names violate PS approved-verb convention**
File: install.ps1:50-57, 60, 97, 137, 158, 172, 185
Affected: `Say`, `Ok`, `Warn`, `Die`, `Ensure-Tools` (unapproved verb `Ensure`),
`Health`, `Next-Steps`.
Not a correctness issue in a standalone script (no module export), but a linting
tool (PSScriptAnalyzer) will flag unapproved verbs. Consistent names like
`Write-Status`, `Write-Ok`, `Write-Warning`, `Invoke-PreFlight` reduce noise if the
scripts are ever linted in CI.

**n-2 — schedule_windows.ps1 creates task objects before the DryRun guard**
File: scripts/schedule_windows.ps1:74-97
`New-ScheduledTaskAction`, `New-ScheduledTaskTrigger`, and
`New-ScheduledTaskSettingsSet` are called at lines 74-85, then the `if ($DryRun)
{ ... exit 0 }` block follows at line 87. These cmdlets are harmless (in-memory
objects, nothing persisted), but with `$ErrorActionPreference = 'Stop'`, any
failure in those three calls (e.g., ScheduledTasks module absent) throws before the
DryRun output is printed. Reorder: check DryRun early and `exit 0` before building
objects (or build objects lazily inside the register block).

**n-3 — install.ps1 -DryRun for claude-desktop actually executes Python**
File: install.ps1:145
When `-DryRun` is combined with the `claude-desktop` command, `Wire-ClaudeDesktop`
runs `& $py $wireScript --repo $HERE --print` (line 145), which is a live Python
process execution. This is parity with the bash version (which also runs `--print`
in dry-run), so the behaviour is intentional, but it violates the user expectation
of "change nothing" for `-DryRun`. A comment in the function making this explicit
would prevent confusion.

**n-4 — Scheduled Task hardcodes powershell.exe, not pwsh.exe**
File: scripts/schedule_windows.ps1:75
The task action uses `"powershell.exe"` — Windows PowerShell 5.1. If a user has
decommissioned PowerShell 5.1 or only has PS 7 (`pwsh.exe`) available (uncommon but
possible on minimally-provisioned Server Core), the task will fail. A comment
explaining that `powershell.exe` is intentional (PS 5.1 for compatibility, the same
version that installs the tool) would be helpful. An optional check could add a
fallback to `pwsh.exe` if `powershell.exe` is absent.

---

## Parity check vs the bash scripts

| Capability | install.sh | install.ps1 | Status |
|---|---|---|---|
| Targets: install / claude-desktop / claude-code / check | Yes | Yes | PASS |
| Unknown-command error | Silent (no default case) | Die with message | PS is stricter — acceptable |
| -DryRun / --dry-run flag | --dry-run arg | -DryRun switch | PASS |
| uv fallback install | curl + sh | Invoke-RestMethod + IEX | PASS (correct Windows equivalent) |
| venv path | .venv/bin/python | .venv\Scripts\python.exe | PASS |
| Package install | uv pip install -e '.[all,dev]' | uv pip install -e ".[all,dev]" | PASS |
| LASTEXITCODE checked after uv | No (set -e does it) | Yes (explicit checks) | PASS — PS version is more explicit |
| Config copy — never clobber | Yes | Yes | PASS |
| data/runs dir created | mkdir -p data data/runs | New-Item -Force ..\runs (creates data too) | PASS |
| .env copy — never clobber | Yes | Yes | PASS |
| claude-desktop DryRun runs python --print | Yes | Yes | PASS |
| claude-code message (uv run form) | Shows .venv/bin/python (stale message) | Shows uv run | PS message is MORE accurate — acceptable |
| Health check via python -m lcp.cli doctor | Yes | Yes | PASS |
| Next-steps uses OS-correct paths | .venv/bin/lcp | .venv\Scripts\lcp.exe | PASS |
| -Help flag | Not present | Present (extra feature) | PASS |

| Capability | run_daily.sh | run_daily.ps1 | Status |
|---|---|---|---|
| lcp.exe / console-script primary | Yes (lcp script) | Yes (lcp.exe) | PASS |
| python -m lcp.cli fallback | No | Yes | PS is more resilient — acceptable |
| Proxy check -> jobs fetch -> jobs rank | Yes | Yes | PASS |
| Continue past individual failures | Yes (|| echo) | Yes (Continue + LASTEXITCODE check) | PASS |
| Timestamps in output | Yes | Yes | PASS |
| Log to file | No (launchd captures stdout) | Yes (Add-Content) | ACCEPTABLE — compensates for Task Scheduler not having StandardOutPath |
| DryRun mode | Not present | Present | Extra feature — PASS |
| DryRun writes log file | N/A | YES — side-effect (see m-1) | MINOR FAIL |

| Capability | schedule_macos.sh | schedule_windows.ps1 | Status |
|---|---|---|---|
| Register daily scheduler | launchctl/plist | Register-ScheduledTask | PASS |
| Unregister | launchctl unload + rm plist | Unregister-ScheduledTask | PASS |
| DryRun | Yes | Yes | PASS |
| Idempotent | Yes (unload before load) | Yes (unregister-then-register) | PASS |
| Default schedule time | 08:30 | 09:00 | MISMATCH (see m-2) |
| stdout/stderr capture to file | Yes (StandardOutPath/StandardErrorPath) | No (see m-4) | PARTIAL GAP |
| data/runs dir creation | Yes | Yes | PASS |
| No launchctl/plutil calls | N/A | Confirmed absent | PASS |
| Admin-rights caveat surfaced | N/A | Yes — documented in header | PASS |
| Custom Hour/Minute params | No (hardcoded) | Yes (-Hour, -Minute) | PS has extra feature — acceptable |

---

## PS 5.1 syntax compatibility summary

Checked for PS7-only constructs:

| Construct | Present? | Assessment |
|---|---|---|
| Ternary `?:` | No | PASS |
| Null-coalescing `??` | No | PASS |
| Pipeline operators `&&` / `\|\|` | No | PASS |
| Get-Content -AsByteStream | No | PASS |
| clean{} block | No | PASS |
| ForEach-Object -Parallel | No | PASS |
| [ScriptBlock]::Create parse | Will succeed (encoding caveat applies to output only, not parsing) | PASS with caveat |
| ScheduledTasks module cmdlets | Used; module available Windows 8+ / PS 5.1+ | PASS |
| New-ScheduledTaskAction -WorkingDirectory | Used; available since module introduction | PASS |
| Array splatting @var | Used correctly in run_daily.ps1:52,55 | PASS |
| $script: scope prefix | Used correctly in run_daily.ps1:47,51,52 | PASS |
| -f format operator | Used in schedule_windows.ps1:43 | PASS |
| New-TimeSpan -Hours | Used in schedule_windows.ps1:84 | PASS |

No PS 7-exclusive syntax was found. All three files are statically compatible with
Windows PowerShell 5.1.

---

## Finding count by severity

BLOCKER: 0
MAJOR: 1
MINOR: 4
NIT: 4
Total: 9
