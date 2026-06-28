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
- **Wake 0** (2026-06-28): grounded via portability audit; authored GOAL + Evaluation Plan +
  this ledger. Design fixed: `uv run` `.mcp.json` for Code, absolute interpreter for Desktop,
  central `lcp.paths.venv_python`. Next: run eval/ledger gates, surface Gate 1, dispatch D2→D1.
