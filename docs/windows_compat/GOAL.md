# GOAL — Windows compatibility for linkedin-coffee-pipeline

**Date:** 2026-06-28
**Skill:** set-work-loops (standard tier — cross-cutting compat; not an agent-behavior change)
**Repo:** linkedin-coffee-pipeline (remote: job-search-tool-claude)
**Maker ≠ Checker:** implementer subagents draft; a fresh-context reviewer verifies (D-Review).

---

## The ask (verbatim)

> Please update the installer and other parts of the repo to also work easily on Windows
> boxes. Check where Mac/Linux assumptions slipped in and make sure there is an alternate
> windows path that works instead. Tell me: what needs implementation, how it will be done,
> what the test for checking it is done is. Show me the final result. /set-work-loops This is
> for the linkedin coffee finder project.

## Interpretation & scope

Make the repo **install and run on Windows as easily as on macOS**, without regressing the
mac/linux path. "Easily" = a non-git user can run one command in PowerShell and get a working
install wired into Claude Desktop and/or Claude Code. Concretely: a PowerShell installer at
parity with `install.sh`; OS-correct interpreter + Claude-config paths everywhere; Windows
daily-run + scheduling scripts; tests that pass on Windows; docs with a Windows section; and a
**real Windows CI run** as the proof.

**In scope:** installer, MCP/Desktop wiring, scheduler scripts, path resolution, tests using
POSIX-only constructs, docs, line-ending hygiene, CI.
**Out of scope:** new pipeline features; changing scraper behavior; Linux scheduler (already a
documented `cron` note). Production `src/lcp/*.py` is already pathlib-clean (audit confirmed) —
only the two POSIX leaks (a `/tmp` test fixture, a docstring) are touched.

## Grounding (audit summary)

A full portability audit (Explore agent, 2026-06-28) found **no existing Windows support** and
these blockers: 4 bash `.sh` scripts (installer, run_daily, schedule_macos, test_install_dryrun);
6 hardcoded `.venv/bin/python` paths (install.sh ×4, `.mcp.json`, `wire_claude_desktop.py:37`);
2 `/tmp` paths (one in a **test**, one in a docstring); macOS-only `plutil`/`launchctl`. Majors:
README + `docs/CLAUDE_DESKTOP.md` are mac-only. Minors: two mac-mentioning comments. The full
inventory is the baseline for AC coverage.

---

## Deliverables (coupled) + DAG

```
D2 (paths helper) ──► D1 (install.ps1 uses it) ──► D5 (CI runs D1)
        │                                              ▲
        ├──► D3 (tests/code) ──────────────────────────┤
        └──► D4 (docs/.gitattributes) ─────────────────┘
```

- **D2 — cross-platform paths (foundation).** Add `lcp.paths.venv_python(repo)`,
  `venv_bin_dir(repo)`, `venv_script(repo, name)` (Scripts/`*.exe` on `nt`, bin/`*` on posix).
  Fix `wire_claude_desktop.py:37` to use it (absolute interpreter for Desktop). Switch committed
  `.mcp.json` to the portable `uv run` form (no per-OS rewrite). Keep `default_config_path()`'s
  existing OS switch.
- **D1 — `install.ps1` (Windows installer parity).** PowerShell mirror of `install.sh`:
  ensure uv (`irm https://astral.sh/uv/install.ps1 | iex` fallback), `uv venv`, `uv pip install
  --python .venv\Scripts\python.exe -e ".[all,dev]"`, config copy (never clobber), `data\runs`,
  targets `install|claude-desktop|claude-code|check`, `-DryRun`, next-steps. Plus `run_daily.ps1`
  and `schedule_windows.ps1` (`Register-ScheduledTask`) at parity with the mac scripts.
- **D3 — Windows-safe tests + residual code/doc leaks.** Replace `/tmp/fake-repo` in
  `tests/test_claude_desktop_config.py` with `tmp_path`. Fix the `cli.py` `/tmp` docstring and
  the two mac-only comments. Confirm no other POSIX-only construct in shipped code.
- **D4 — `.gitattributes` + docs.** `.gitattributes` enforcing LF for `*.sh`/`*.py`/text and
  CRLF for `*.ps1`/`*.bat`. Windows install sections in `README.md` and `docs/CLAUDE_DESKTOP.md`.
- **D5 — tests, gate, real CI proof.** Cross-platform unit tests for the D2 resolvers
  (monkeypatched `os.name`). A repo gate `scripts/gates/gate_no_posix_assumptions.py` that fails
  if a shipped config/script reintroduces an un-guarded `.venv/bin` or `/tmp`. A GitHub Actions
  **`windows-latest`** workflow that runs `install.ps1`, `pytest`, `lcp --help`, and
  `lcp mcp --selfcheck` on a real Windows box.

---

## Acceptance criteria (AC-NNN: scenario / action / expected / must-not / verification / priority)

**AC-001 — Windows installer exists and is parsable.**
scenario: A Windows user has only PowerShell. · action: inspect `install.ps1`. · expected: it
exists, has `install|claude-desktop|claude-code|check` targets + `-DryRun`, no bash-isms. ·
must-not: shell out to `bash`/`sh`/`curl`. · **verification:** `test -f install.ps1` AND the D5
CI job parses it (`[ScriptBlock]::Create((Get-Content install.ps1 -Raw))` exits 0). · priority: P0

**AC-002 — Installer creates a working venv + install on Windows.**
scenario: fresh clone on windows-latest. · action: `./install.ps1`. · expected: `.venv\Scripts\
python.exe` exists and `import lcp` works; `lcp --help` exits 0. · must-not: reference
`.venv/bin`. · **verification:** D5 CI step `./install.ps1` then `.venv\Scripts\lcp.exe --help`
exits 0. · priority: P0

**AC-003 — OS-correct interpreter resolver.**
scenario: code needs the venv python. · action: call `lcp.paths.venv_python(repo)`. · expected:
`...\.venv\Scripts\python.exe` when `os.name=='nt'`, `.../.venv/bin/python` otherwise. ·
must-not: hardcode `bin`. · **verification:** `pytest tests/test_paths_platform.py` (monkeypatches
`os.name`) — green on mac now, on Windows in CI. · priority: P0

**AC-004 — `.mcp.json` works on Windows (Claude Code).**
scenario: open repo in Claude Code on Windows. · action: read `.mcp.json`. · expected: a command
that resolves with no `bin`-vs-`Scripts` assumption (the `uv run` form). · must-not: contain
`.venv/bin/python`. · **verification:** `gate_no_posix_assumptions.py` passes AND CI runs the
exact `.mcp.json` command and `lcp.mcp_server` selfcheck exits 0 on Windows. · priority: P0

**AC-005 — Claude Desktop wiring writes an OS-correct absolute interpreter.**
scenario: `install.ps1 claude-desktop` on Windows. · action: run wiring `--print`. · expected:
`command` ends with `\.venv\Scripts\python.exe`; config target is `%APPDATA%\Claude\...`. ·
must-not: emit a `bin/python` path or clobber existing servers. · **verification:**
`pytest tests/test_claude_desktop_config.py` (incl. an `os.name=='nt'` case) green; CI runs
`wire_claude_desktop.py --print` on Windows and greps for `Scripts`. · priority: P0

**AC-006 — Full test suite passes on Windows.**
scenario: CI on windows-latest. · action: `pytest -q`. · expected: all tests pass (no `/tmp`
fixture failures). · must-not: any test hardcode `/tmp`. · **verification:** D5 CI `pytest` step
exits 0 on windows-latest. · priority: P0

**AC-007 — Windows daily-run + scheduling parity.**
scenario: a Windows user wants the daily core. · action: inspect `run_daily.ps1` +
`schedule_windows.ps1`. · expected: both exist; `run_daily.ps1` runs the venv `lcp` stages;
`schedule_windows.ps1` registers a Scheduled Task. · must-not: call `launchctl`/`plutil`. ·
**verification:** CI parses both scripts (ScriptBlock) and dry-runs `run_daily.ps1 -DryRun`. ·
priority: P1

**AC-008 — Line-ending hygiene.**
scenario: repo cloned on Windows. · action: read `.gitattributes`. · expected: `*.sh`/`*.py`
forced LF, `*.ps1` CRLF. · must-not: let `.sh` ship CRLF. · **verification:**
`git check-attr text eol -- install.sh install.ps1` shows `eol=lf` / `eol=crlf` respectively. ·
priority: P1

**AC-009 — Docs have a Windows path.**
scenario: a Windows user reads the README. · action: open `README.md` + `docs/CLAUDE_DESKTOP.md`.
· expected: a Windows/PowerShell install section with `.venv\Scripts\...` examples. · must-not:
present only `./install.sh`. · **verification:** `grep -i 'install.ps1' README.md
docs/CLAUDE_DESKTOP.md` matches. · priority: P1

**AC-010 — No mac/linux regression.**
scenario: existing mac users. · action: `pytest` + `./install.sh --dry-run` on mac. · expected:
unchanged green (163+ tests) and dry-run output intact. · must-not: break the posix path. ·
**verification:** local `pytest -q` exits 0 on mac; `./install.sh --dry-run` exits 0. · priority: P0

---

## Evaluation Plan

**How we'll KNOW it works:** the repo installs and its full test suite + MCP selfcheck pass on a
**real `windows-latest` GitHub Actions runner**, while the macOS path stays green. Pass bar: D5 CI
job is green (all P0 ACs) AND local mac `pytest` stays green. Falsifier: any P0 AC's verification
command exits non-zero, or CI shows a `.venv/bin`/`/tmp` failure on Windows.

**Per-capability BINARY scorers** (code-graders first; no LLM judge needed — every check is
deterministic):

| Capability | Scorer (binary) | Type | AC |
|---|---|---|---|
| Installer runs on Windows | `install.ps1` exits 0 + `lcp --help` exits 0 on windows-latest | code (CI) | 001,002 |
| Interpreter path resolver | `pytest tests/test_paths_platform.py` exits 0 (both `os.name`) | code | 003 |
| Claude Code config portable | `.mcp.json` command runs on Windows; selfcheck exits 0; gate passes | code (CI+gate) | 004 |
| Desktop wiring OS-correct | `pytest tests/test_claude_desktop_config.py` exits 0 incl. nt case | code | 005 |
| Suite green on Windows | `pytest -q` exits 0 on windows-latest | code (CI) | 006 |
| Scheduling parity | both `.ps1` parse + `run_daily.ps1 -DryRun` exits 0 | code (CI) | 007 |
| Line endings | `git check-attr` shows lf/crlf as specified | code | 008 |
| Docs Windows path | `grep install.ps1` matches in README + desktop doc | code | 009 |
| No mac regression | mac `pytest -q` + `./install.sh --dry-run` exit 0 | code | 010 |
| No POSIX leak reintroduced | `gate_no_posix_assumptions.py` exits 0 | code (gate) | 004,006 |

**Golden/seed set:** the audit inventory (every offending file:line) is the seed — each fixed
item maps to an AC scorer above. New regressions are caught by `gate_no_posix_assumptions.py`.

**Observability hooks (standard tier — light):** structured pass/fail from each gate + the CI job
summary (per-step exit codes). No new runtime instrumentation needed (not a behavior change).

**Report artifacts (what the human sees):** (1) the windows-latest CI run URL + green check, (2)
a before/after table of audit blockers → fix → scorer, (3) the asked-vs-done diff.

---

## Operating rules

- Implementer subagents (Sonnet) draft D1/D3/D4; I (Opus) own D2 (the shared helper — cross-cutting)
  + D5 gate/CI + the review. Each impl step ends in a reviewer-class check.
- Commit with explicit pathspecs only; never `git add -A` (secrets hygiene from prior build).
- No secrets/PII/local absolute paths in anything committed (carried-over hard rule).
- Gate scripts are append-only; never weaken to get green.

## Definition of Done

All P0 ACs green (incl. the windows-latest CI job), P1 ACs green, mac path unregressed, a
separate-context review with no unresolved blocking verdict, and a final report with an
asked-vs-done diff + a `## Did it actually work? (evidence)` section linking the CI run. Pushed to
the remote.

## Open Questions / Assumptions ledger

- **OQ-1 (assumed):** Claude Code on Windows is launched from a shell where `uv` is on PATH, so
  the `uv run` `.mcp.json` resolves. *Default chosen:* portable `uv run` form for Code; explicit
  absolute interpreter for Desktop (GUI, no PATH). Fallback (explicit interpreter `.mcp.json`)
  documented. Revisit if CI selfcheck fails.
- **OQ-2 (assumed):** Windows scheduling via `Register-ScheduledTask` (PowerShell) is acceptable;
  not blocking the daily-core (which runs by hand too). P1.
- **OQ-3 (assumed):** No need to support legacy Windows PowerShell 5.1 quirks beyond what
  windows-latest ships (PS 5.1 + PS 7 both present on the runner); installer written to run under
  5.1-compatible syntax to be safe.
