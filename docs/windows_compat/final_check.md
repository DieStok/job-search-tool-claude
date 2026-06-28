# Final check — asked vs delivered (Windows compatibility)

## INITIAL ASK (verbatim)
> Please update the installer and other parts of the repo to also work easily on Windows boxes.
> Check where Mac/Linux assumptions slipped in and make sure there is an alternate windows path
> that works instead. Tell me: what needs implementation, how it will be done, what the test for
> checking it is done is. Show me the final result.

## DELIVERED (per audit blocker → fix → proof)

| Audit finding (mac/linux assumption) | Severity | Fix delivered | Proof (scorer) |
|---|---|---|---|
| `install.sh` is bash-only; no Windows installer | BLOCKER | `install.ps1` (PS 5.1+ parity: install/claude-desktop/claude-code/check + `-DryRun`) | CI parses + runs it on windows-latest (AC-001/002) |
| 6× hardcoded `.venv/bin/python` (install, `.mcp.json`, wiring) | BLOCKER | central `lcp.paths.venv_python/venv_bin_dir/venv_script`; wiring uses it; `.mcp.json` → portable `uv run` form | `test_paths_platform.py`, gate, CI selfcheck (AC-003/004/005) |
| `wire_claude_desktop.py:37` emits `bin/python` on Windows | BLOCKER | `_venv_python()` → `Scripts\python.exe` on nt | `test_claude_desktop_config.py` nt case + CI grep (AC-005) |
| `run_daily.sh` / `schedule_macos.sh` mac-only (launchd) | BLOCKER | `run_daily.ps1` + `schedule_windows.ps1` (Task Scheduler) | CI parses both + dry-runs (AC-007) |
| `tests/test_claude_desktop_config.py` hardcodes `/tmp` | BLOCKER (test) | `tmp_path` fixture | suite green on windows-latest (AC-006) |
| `cli.py` docstring `/tmp/my.csv`; mac-only comments | MINOR | neutralized to relative path; comments generalized | gate + grep |
| README / `docs/CLAUDE_DESKTOP.md` mac-only | MAJOR | Windows (PowerShell) sections added | `grep install.ps1` (AC-009) |
| no line-ending policy (`.sh` could ship CRLF) | (gap) | `.gitattributes`: LF for sh/py, CRLF for ps1 | `git check-attr` (AC-008) |
| no regression guard | (gap) | new POSIX-assumption gate + ubuntu/macos CI matrix | gate + posix CI (AC-010) |

## "What's the test?" (answered, per the ask)
Every fix has a **binary, deterministic** scorer (no LLM judge): the per-AC table in
[GOAL.md](./GOAL.md) `## Evaluation Plan`. The umbrella test = the **windows-latest GitHub Actions
job** actually installing the repo and running the full suite + MCP selfcheck on a real Windows box,
with ubuntu/macos jobs proving no POSIX regression.

## GAP / not done (honest)
- **Local pwsh execution:** PowerShell is not installed on the dev Mac, so the `.ps1` scripts are
  verified by (a) static expert review and (b) the **real windows-latest CI run** — not by local
  execution. This is the intended proof per the GOAL (CI is the terminal gate).
- **Legacy Windows PowerShell 5.1 nuances** beyond what windows-latest ships are not exercised (the
  runner has both 5.1 and 7); scripts were written to 5.1-safe syntax. Assumption logged as OQ-3.
- **Windows scheduling** (`schedule_windows.ps1`) is parsed + dry-run in CI but a live
  `Register-ScheduledTask` is not executed in CI (needs elevation); the daily core also runs by hand.
