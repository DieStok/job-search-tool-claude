# Final report — Windows compatibility for linkedin-coffee-pipeline

**Date:** 2026-06-28 · **Tier:** standard · **Skill:** set-work-loops
**Goal doc:** [GOAL.md](./GOAL.md) · **Ledger:** [LEDGER.md](./LEDGER.md) · **Asked-vs-done:** [final_check.md](./final_check.md)

## What was asked (verbatim)
> Please update the installer and other parts of the repo to also work easily on Windows boxes.
> Check where Mac/Linux assumptions slipped in and make sure there is an alternate windows path
> that works instead. Tell me: what needs implementation, how it will be done, what the test for
> checking it is done is. Show me the final result.

## What was done
A portability audit found **no existing Windows support** and 11 concrete leak classes (4 bash-only
scripts, 6 hardcoded `.venv/bin/python` paths, 2 `/tmp` paths, macOS-only `launchctl`/`plutil`,
mac-only docs, no line-ending policy). Five coupled deliverables fixed them without touching the
already-clean production `src/lcp` decision logic:

- **D1 — Windows scripts:** `install.ps1` (PS 5.1+ parity with `install.sh`: `install` /
  `claude-desktop` / `claude-code` / `check` + `-DryRun`), `scripts/run_daily.ps1`, and
  `scripts/schedule_windows.ps1` (Task Scheduler, the launchd equivalent).
- **D2 — cross-platform paths:** `lcp.paths.venv_python / venv_bin_dir / venv_script` (single source
  of truth, `os.name=='nt'` discriminator); `wire_claude_desktop.py` now emits an OS-correct absolute
  interpreter; `.mcp.json` switched to the portable `uv run --no-sync python -m lcp.mcp_server` form
  (no `bin`-vs-`Scripts` assumption at all).
- **D3 — Windows-safe tests + residual leaks:** `/tmp` test fixture → `tmp_path`; `cli.py` docstring
  + two mac-only comments neutralized.
- **D4 — line endings + docs:** `.gitattributes` (LF for `*.sh`/`*.py`, CRLF for `*.ps1`); Windows
  (PowerShell) sections in `README.md` and `docs/CLAUDE_DESKTOP.md`.
- **D5 — tests, gate, real CI:** `tests/test_paths_platform.py` (both OS layouts via monkeypatch),
  `scripts/gates/gate_no_posix_assumptions.py` (forbids `.venv/bin` + `/tmp/` in shipped
  cross-platform files; fails-closed on empty input), and `.github/workflows/cross-platform.yml`
  that installs + tests on a **real windows-latest runner** (+ ubuntu/macos regression matrix).

## Review outcomes (separate-context, Maker ≠ Checker)
- **PowerShell review** ([review_powershell.md](./reviews/review_powershell.md)): APPROVE-WITH-NITS,
  0 blockers. 1 MAJOR (Unicode-glyph mojibake on PS 5.1) → **fixed** (ASCII markers). 4 MINORs folded.
- **Core review** ([review_core.md](./reviews/review_core.md)): APPROVE-WITH-NITS, 0 blockers/majors.
  3 MINORs + 2 NITs folded (gate widened to `scripts/*.py`; CI uses the literal module command;
  README ops examples gained a Windows block).
- All findings resolved; `gate_work_reviewed` green for D1–D5.

## Drift (asked vs done)
No scope drift. Everything asked was delivered; the only conscious *additions* beyond the literal ask
are the regression matrix (ubuntu/macos) and the POSIX-assumption gate — both serve "make sure the
windows path works instead" by preventing silent re-breakage. Honest gaps (in
[final_check.md](./final_check.md)): the `.ps1` are proven by static expert review + real Windows CI
rather than local execution (no pwsh on the dev Mac — by design, CI is the terminal gate); a live
`Register-ScheduledTask` is parsed/dry-run in CI, not executed (needs elevation).

## Implementation overview
The crux was the one-static-path-can't-be-both problem for the venv interpreter. Resolved by splitting
on launch environment: **Claude Code** (terminal-launched, uv on PATH) uses the portable `uv run`
`.mcp.json` — zero per-OS rewrite; **Claude Desktop** (GUI, unreliable PATH) gets an explicit absolute
`.venv\Scripts\python.exe` written by `wire_claude_desktop.py`. A single `lcp.paths` helper is the
only place that knows the `bin`-vs-`Scripts` rule, and it is unit-tested on both branches regardless of
host OS (monkeypatched predicate), so a Mac CI covers the Windows branch and vice-versa.

## Did it actually work? (evidence)
Per-capability binary scorers from the [Evaluation Plan](./GOAL.md) — all measured locally on macOS;
the Windows-only ones are measured by the CI job:

| Scorer (metric) | Result | Where |
|---|---|---|
| Full test suite (incl. 11 new platform tests) | **169 passed** | `pytest -q` (macOS, local) |
| `lcp.paths` resolver — both OS layouts | **green** (posix + windows branch) | `tests/test_paths_platform.py` |
| Desktop wiring emits OS-correct interpreter | simulated-nt → `…/.venv/Scripts/python.exe` | `test_claude_desktop_config.py` nt case |
| `.mcp.json` launcher resolves + selfchecks | **rc=0, 8 tools (2 gated)** | `uv run --no-sync python -m lcp.mcp_server --selfcheck` |
| POSIX-assumption gate over shipped files | **PASS, 41 files, 0 leaks** | `gate_no_posix_assumptions.py` |
| Gate is non-vacuous | **detects planted leak; fails-closed on empty input** | gate self-test |
| `.ps1` are mojibake-safe | **pure ASCII** (byte scan) | `grep -P '[\x80-\xff]'` → none |
| No mac regression | suite green + `./install.sh --dry-run` intact | local |
| set-work-loops delivery gates | eval-plan ✅ ledger ✅ work-reviewed ✅ final-check ✅ | skill gates |

**Real-Windows proof:** the `windows-latest` CI job runs `install.ps1` → `lcp --help` → `pytest` →
MCP selfcheck (module form) → Desktop-wiring grep → the gate, on an actual Windows box. CI run result
+ URL appended below once the push triggers it.

**✅ CI RESULT — `success` on all platforms** (run
[28330938219](https://github.com/DieStok/job-search-tool-claude/actions/runs/28330938219), PR #1):

| Job | Result |
|---|---|
| **windows-latest** (installer + suite + MCP) | ✅ success |
| ubuntu-latest (regression) | ✅ success |
| macos-latest (regression) | ✅ success |

Every windows-latest step passed on a **real Windows runner**: Install uv → Set up Python → **Parse
PowerShell scripts** → **Run install.ps1** → **lcp --help** → **pytest** (full suite) → **MCP
selfcheck (server module)** → **MCP selfcheck via the exact `.mcp.json` launcher** → **Desktop wiring
emits a Windows `Scripts\python.exe`** → **POSIX-assumption gate**.

*First CI run (28330749730) caught one defect — a CI-assertion bug, not a product bug: PowerShell's
`-notmatch` on a multi-line array returns the non-matching elements (truthy) rather than a boolean, so
the wiring step false-threw even though it had emitted the correct `…\.venv\Scripts\python.exe`. Fixed
by joining before matching. Branching (not pushing to `main`) kept the default branch clean while this
was resolved.*

## Output artifact paths to changed files (what changed)
- New: `install.ps1`, `scripts/run_daily.ps1`, `scripts/schedule_windows.ps1`,
  `tests/test_paths_platform.py`, `scripts/gates/gate_no_posix_assumptions.py`,
  `.github/workflows/cross-platform.yml`, `.gitattributes`,
  `docs/windows_compat/{GOAL,LEDGER,FINAL_REPORT,final_check}.md` + `reviews/`.
- Changed: `src/lcp/paths.py`, `scripts/wire_claude_desktop.py`, `.mcp.json`,
  `tests/test_claude_desktop_config.py`, `README.md`, `docs/CLAUDE_DESKTOP.md`,
  `src/lcp/cli.py` (docstring), `.env.example` + `pyproject.toml` (comments).

## ECC / skill tuning (compound-to-memory)
- **Reusable pattern:** the `bin`-vs-`Scripts` split via a single monkeypatchable predicate lets one
  host's CI cover the other OS's branch — worth reusing for any cross-platform path code.
- **Gate lesson (re-confirmed):** the POSIX gate first false-flagged its own documentation; the fix was
  an explicit, greppable `posix-ok` per-line marker rather than loosening the check — keep gates strict
  with a visible escape hatch, and always prove the gate catches a *planted* leak + fails-closed on
  empty input before trusting it (gotcha #10).
