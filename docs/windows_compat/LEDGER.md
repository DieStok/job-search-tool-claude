# LEDGER — Windows compatibility

Goal doc: [GOAL.md](./GOAL.md)

## Routing decision
- **Tier:** standard (cross-cutting compat across installer/configs/scripts/docs/tests; NOT an
  agent-behavior change → no trajectory/pass^k ceremony, observability = light pass/fail + CI).
- **Why:** changes how the system *installs/runs per-OS*, touches many files, but production
  decision-logic is untouched. Behavior-override does not apply (no runtime decision change).

## Workstream status
| ID | Deliverable | Owner | Status |
|----|-------------|-------|--------|
| D2 | cross-platform paths helper + `.mcp.json` + desktop wiring | Opus | pending |
| D1 | install.ps1 + run_daily.ps1 + schedule_windows.ps1 | Sonnet sub | pending |
| D3 | Windows-safe tests + residual leaks | Sonnet sub | pending |
| D4 | .gitattributes + docs | Sonnet sub | pending |
| D5 | path tests + posix gate + windows-latest CI | Opus | pending |
| D-Review | separate-context review + final report | fresh ctx | pending |

## Circuit breakers / bounds
- Max ~2 autonomous build passes per deliverable; plateau (3 non-improving) → escalate.
- CI is the terminal proof; if windows-latest fails identically 2× on the same cause → escalate.
- Stop the loop + usage-poll when all ACs green and report written (no idle timer).

## Wake log
- **Wake 3** (2026-06-28): re-run 28330938219 GREEN on ALL platforms (windows-latest + ubuntu +
  macos). Stamped CI evidence into FINAL_REPORT. **All ACs met; loop complete.** Stopping the
  usage-poll/wakeup (no active task remains).
- **Wake 2** (2026-06-28): CI run 28330749730 — ubuntu+macos GREEN; windows-latest installer/pytest/
  both MCP selfchecks/ps1-parse ALL GREEN; only the "Desktop wiring" *assertion* false-threw (PowerShell
  `-notmatch` on a multi-line array returns elements, not bool — product output was correct
  `...\Scripts\python.exe`). Fixed the assertion (join then match; also assert no POSIX bin). Pushed;
  re-run 28330938219 in_progress. Product is proven on real Windows; awaiting clean green.
- **Wake 1** (2026-06-28): all 5 deliverables built + folded both separate-context reviews
  (APPROVE-WITH-NITS, 0 blockers; MAJOR glyph-mojibake fixed → ASCII). 169 tests green; all 6
  delivery gates pass. Pushed branch `windows-compat`, opened PR #1. windows-latest CI in_progress
  (run 28330749730) — awaiting conclusion to stamp the report's CI evidence. Next: confirm CI green.
- **Wake 0** (2026-06-28): grounded via portability audit; authored GOAL + Evaluation Plan +
  this ledger. Design fixed: `uv run` `.mcp.json` for Code, absolute interpreter for Desktop,
  central `lcp.paths.venv_python`. Next: run eval/ledger gates, surface Gate 1, dispatch D2→D1.
