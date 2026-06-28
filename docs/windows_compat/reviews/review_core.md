VERDICT: APPROVE-WITH-NITS

Review covers deliverable D2 (paths/wiring/.mcp.json), deliverable D3 (tests/leaks), deliverable D4 (.gitattributes/docs), deliverable D5 (gate/CI).

## Resolution (folded by orchestrator, 2026-06-28)
All actionable findings RESOLVED — no unresolved blocking finding remains:
- MINOR-1 (gate didn't scan scripts/*.py): FIXED — gate now scans top-level scripts/*.py (gates/ excluded by design); re-ran clean over 41 files.
- MINOR-2 (CI used `lcp mcp --selfcheck` not the literal module form): FIXED — CI now runs `uv run --no-sync python -m lcp.mcp_server --selfcheck` (verified rc=0).
- MINOR-3 (README "Use it" POSIX-only examples): FIXED — added a Windows PowerShell command block + scheduling note.
- NIT-1 (wire_claude_desktop.py docstring `.venv/bin` unmarked): FIXED — `# posix-ok` added (required now that the gate scans scripts/*.py).
- NIT-2 (spurious posix-ok in test): FIXED — removed.
- NIT-3 (`.mcp.json` env:{} omits LCP_CONFIG): ACCEPTED — `paths.default_config_path()` auto-resolves the live config relative to the package (a feature, not a gap); documented in the final report.

---

Reviewer: separate-context checker (fresh context, did not write this code)
Date: 2026-06-28
Scope: AC-003, AC-004, AC-005, AC-006, AC-008, AC-010 (non-PowerShell deliverables)

---

## Findings

### MINOR-1 — Gate scope excludes `scripts/wire_claude_desktop.py`
**File:** `scripts/gates/gate_no_posix_assumptions.py`, `_targets()` function
**Problem:** The gate scans `.mcp.json`, `*.ps1`, `tests/**/*.py`, and `src/lcp/**/*.py`. It does
NOT scan `scripts/*.py`. `wire_claude_desktop.py` is the cross-platform-critical file fixed by
this very change (it was one of the six hardcoded `.venv/bin` callers in the audit). If a future
contributor adds a real `.venv/bin` assumption to any script under `scripts/` — the most likely
place for such a regression — the gate will not catch it.

The gate's own docstring says it scans "everything that must work on Windows too" but
`scripts/wire_claude_desktop.py` is the canonical counter-example. The current code is correct
(it calls `lcp.paths.venv_python`), so this is not a present defect, but it is an unguarded
regression path.

**Suggested fix:** Add `files += sorted((repo / "scripts").glob("*.py"))` to `_targets()`,
then add `# posix-ok` to the docstring line in `wire_claude_desktop.py:36` and the fallback's
POSIX branch (line 48 uses Path division, not a string literal, so `.venv/bin` won't appear as
a token there — no marker needed on that line). The allowlist already handles `.sh` files.

---

### MINOR-2 — CI proof of AC-004 does not run the exact `.mcp.json` command
**File:** `.github/workflows/cross-platform.yml`, line 63
**Problem:** The "MCP selfcheck via .mcp.json launcher form" step runs:

    uv run --no-sync lcp mcp --selfcheck

The `.mcp.json` entry point is:

    uv run --no-sync python -m lcp.mcp_server

These are different entry points. The CLI route (`lcp mcp --selfcheck`) exercises the typer/click
dispatch layer on top of the module. The module-direct route (`python -m lcp.mcp_server`) checks
`"--selfcheck" in sys.argv` in `main()`. Both exercise the same underlying selfcheck, but the CI
step does not prove the exact invocation path that Claude Code will actually use.

Concretely: the CI confirms `uv run --no-sync` resolves on Windows and that the MCP code works
via the CLI, but it does not confirm that `python -m lcp.mcp_server` is reachable through `uv run`
on Windows.

**Suggested fix:** Change the step to:

    uv run --no-sync python -m lcp.mcp_server --selfcheck

This proves the exact `.mcp.json` command, not just a proxy. The `--selfcheck` flag is supported
in `mcp_server.py:169`.

---

### MINOR-3 — README "Use it" section retains POSIX-only operation commands
**File:** `README.md`, lines 88-92
**Problem:** The "Use it" section shows only `.venv/bin/lcp` commands:

    .venv/bin/lcp jobs fetch
    .venv/bin/lcp jobs rank
    .venv/bin/lcp doctor

There is no Windows equivalent shown. The Windows install section (AC-009) exists and is correct,
but a Windows user who reads the README past the install step hits POSIX-only examples for daily
operation.

This does not fail AC-009 (which only requires an install section) but it creates friction and
risks a user attempting `.venv/bin/lcp` on Windows.

**Suggested fix:** Add a tabbed or split block:

    # macOS / Linux
    .venv/bin/lcp jobs fetch
    # Windows
    .venv\Scripts\lcp.exe jobs fetch

Or use `uv run --no-sync lcp jobs fetch` as a portable alternative for both sections.

---

### NIT-1 — `wire_claude_desktop.py:36` docstring contains `.venv/bin` without `posix-ok`
**File:** `scripts/wire_claude_desktop.py`, line 36
**Problem:** The `_venv_python` docstring reads:

    """OS-correct venv interpreter (.venv\\Scripts\\python.exe on Windows, .venv/bin/python on POSIX).

This contains the literal string `.venv/bin`. The gate does not scan this file today (MINOR-1
above), so this is not currently flagged. However, if the gate's scope is ever widened to include
`scripts/*.py`, this line would need `# posix-ok` to silence a legitimate false-positive. Adding
the marker now prevents a future confusing gate failure.

**Suggested fix:** Append `# posix-ok` to line 36.

---

### NIT-2 — Spurious `posix-ok` marker on `test_claude_desktop_config.py:21`
**File:** `tests/test_claude_desktop_config.py`, line 21
**Problem:** The line:

    Uses tmp_path so it is valid on every OS, replacing the old hardcoded fake path."""  # posix-ok

carries the `posix-ok` marker, but the line contains neither `.venv/bin` nor `/tmp/`. No
suppression is needed. The marker is harmless but creates noise for reviewers checking for
marker abuse — it forces them to verify the line contains no real leak.

**Suggested fix:** Remove `# posix-ok` from that line; keep the marker only on lines that
actually contain a forbidden token.

---

### NIT-3 — `env: {}` in `.mcp.json` silently diverges from the Desktop entry's `LCP_CONFIG`
**File:** `.mcp.json`, line 6; `scripts/wire_claude_desktop.py`, line 57
**Problem:** The Desktop entry sets `"env": {"LCP_CONFIG": "<repo>/config/config.yaml"}`. The
Code entry sets `"env": {}` (no `LCP_CONFIG`). The server falls back to
`paths.default_config_path()` (which resolves via `Path(__file__).resolve().parents[2]`, so it
works correctly from any cwd). This is a valid design choice documented in OQ-1, but the
divergence is undocumented in the `env: {}` comment and could confuse a future maintainer who
wonders why the Desktop entry was the only one to set it.

**Suggested fix:** Add an inline comment: `"env": {}` with a trailing comment explaining the
fallback, e.g. `// LCP_CONFIG not set; server falls back to paths.default_config_path() (package-relative)`.
JSON doesn't support comments natively, so a one-line note in `.mcp.json`'s docstring or in
`docs/CLAUDE_DESKTOP.md` would be more appropriate.

---

## AC coverage

**AC-003 — OS-correct interpreter resolver**
COVERED. `lcp.paths.venv_python/venv_bin_dir/venv_script` correctly branch on `_is_windows()`
(`os.name == "nt"`, matching stdlib venv). `test_paths_platform.py` monkeypatches both branches
and asserts directory name ("Scripts" vs "bin") and filename ("python.exe" vs "python"). No
caller in `src/lcp/` or `tests/` hardcodes `bin` (gate verified). The wire script uses the
helper or the correctly branched fallback. Minor gate scope gap noted (MINOR-1) but does not
affect present correctness.

**AC-004 — `.mcp.json` works on Windows**
MOSTLY COVERED. `.mcp.json` contains no `bin` path (gate passes). The CI Windows job proves
`uv run --no-sync` resolves and the MCP code runs. Gap: the CI step runs `lcp mcp --selfcheck`
not `python -m lcp.mcp_server --selfcheck`, so the exact module-invocation path from `.mcp.json`
is not literally proven on Windows (MINOR-2). `env: {}` is safe because `load_config(None)` has
a correct fallback (NIT-3).

**AC-005 — Claude Desktop wiring writes OS-correct absolute interpreter**
COVERED. `wire_claude_desktop.py` delegates to `lcp.paths.venv_python` for the primary path.
`test_claude_desktop_config.py` tests both `nt` (asserts `python.exe` + `Scripts` + no `bin`
parts) and POSIX (asserts `python` + `bin` + no `Scripts` parts) by monkeypatching
`lcp.paths._is_windows`. The monkeypatch correctly propagates through the import chain.
CI greps `Scripts` in the `--print` output on the Windows runner.

**AC-006 — Full test suite passes on Windows**
COVERED. The `/tmp` fixture in `test_claude_desktop_config.py` is replaced with `tmp_path`.
Gate forbids `/tmp/` in `tests/**/*.py` with no discovered occurrences. CI runs `pytest -q` on
windows-latest. No other `/tmp` or POSIX-only construct found in the test corpus.

**AC-008 — Line-ending hygiene**
COVERED. `.gitattributes` enforces `*.sh eol=lf`, `*.py eol=lf`, `*.yaml/yml eol=lf`,
`*.json eol=lf`, `*.ps1 eol=crlf`, `*.bat/cmd eol=crlf`. The `text=auto` global and explicit
overrides follow git best-practice ordering. The `install.sh` eol=lf and `install.ps1` eol=crlf
mapping satisfies the AC literally.

**AC-010 — No mac/linux regression**
COVERED. The posix CI matrix job (ubuntu-latest + macos-latest) runs install, pytest, and the
gate. All new tests use monkeypatching rather than live platform detection, so they are
host-neutral and do not affect the POSIX result. `venv_python()` on POSIX continues to return
`bin/python`. No existing test was removed or weakened.
