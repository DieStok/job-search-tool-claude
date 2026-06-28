#!/usr/bin/env python3
"""Gate: no POSIX-only assumption leaks into a cross-platform-critical shipped file.

Windows-compat backstop (docs/windows_compat/GOAL.md, AC-004/AC-006). The repo
intentionally keeps POSIX-only scripts (`install.sh`, `scripts/run_daily.sh`,
`scripts/schedule_macos.sh`) — those are ALLOWLISTED. Everything that must work on
Windows too is scanned for forbidden tokens:

  - ``.venv/bin``  — the POSIX venv layout; Windows uses ``.venv\\Scripts``. A leak
    here breaks the MCP launcher / wiring on Windows.
  - hardcoded ``/tmp/`` — absent on Windows; tests/code must use ``tmp_path`` /
    ``tempfile`` instead.

Scanned (cross-platform-critical):
  - ``.mcp.json``                      (Claude Code launcher)
  - every ``*.ps1``                    (Windows scripts must not carry POSIX paths)
  - every ``tests/**/*.py``            (must run on Windows CI — no hardcoded /tmp)
  - every ``src/lcp/**/*.py``          (production code — pathlib only, no /tmp literal)

STRUCTURAL/shape-only by design: it greps for the offending tokens, it does not
judge intent. It fails CLOSED on its own inputs — if NO file was scanned (glob
returned nothing), that is a FAIL, never a vacuous pass (gotcha #10: a gate whose
inputs are empty must fail, not pass). Pure-Python, stdlib only, exits 0/1.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gatelib import GateResult, emit, read_text  # noqa: E402

# Files that are INTENTIONALLY POSIX-only — never scanned for these tokens.
ALLOWLIST = {
    "install.sh",
    "scripts/run_daily.sh",
    "scripts/schedule_macos.sh",
    "scripts/test_install_dryrun.sh",
}

FORBIDDEN = {
    ".venv/bin": "POSIX venv layout — Windows uses .venv\\Scripts (use lcp.paths.venv_python)",
    "/tmp/": "hardcoded POSIX temp dir — use tmp_path / tempfile.gettempdir() instead",
}

# A line may opt out (e.g. a docstring/comment that MENTIONS the POSIX path while
# explaining the cross-platform handling, or a test that asserts the POSIX branch)
# by carrying this marker. It is explicit, greppable, and reviewer-visible — the
# separate-context reviewer checks it is not abused to wave through a real leak.
ALLOW_MARKER = "posix-ok"


def _targets(repo: Path) -> list[Path]:
    files: list[Path] = []
    mcp = repo / ".mcp.json"
    if mcp.exists():
        files.append(mcp)
    files += sorted(repo.glob("*.ps1"))
    files += sorted((repo / "scripts").glob("*.ps1"))
    files += sorted((repo / "tests").rglob("*.py"))
    files += sorted((repo / "src" / "lcp").rglob("*.py"))
    # top-level scripts/*.py (e.g. wire_claude_desktop.py — a fixed bin caller).
    # NB: scripts/gates/*.py are excluded on purpose — the gate sources legitimately
    # contain the forbidden token strings as the patterns they search for.
    files += sorted((repo / "scripts").glob("*.py"))
    # de-dup, drop allowlisted
    seen: set[Path] = set()
    out: list[Path] = []
    for f in files:
        if f in seen:
            continue
        seen.add(f)
        rel = f.relative_to(repo).as_posix()
        if rel in ALLOWLIST:
            continue
        out.append(f)
    return out


def check_no_posix_assumptions(repo: Path) -> GateResult:
    res = GateResult(name="gate_no_posix_assumptions", passed=True)
    targets = _targets(repo)

    # Fail closed on empty input (gotcha #10).
    if not targets:
        res.passed = False
        res.reasons.append("no cross-platform-critical files were scanned — fail-closed")
        res.checks.append(("scanned >=1 file", False))
        return res
    res.checks.append((f"scanned {len(targets)} cross-platform-critical file(s)", True))

    leaks: list[str] = []
    for f in targets:
        text = read_text(f)
        rel = f.relative_to(repo).as_posix()
        for token, why in FORBIDDEN.items():
            # only count lines that contain the token AND are not explicitly allowed
            offending = [
                i
                for i, ln in enumerate(text.splitlines(), 1)
                if token in ln and ALLOW_MARKER not in ln
            ]
            if offending:
                leaks.append(f"{rel}:{offending[0]}  contains '{token}'  ({why})")

    if leaks:
        res.passed = False
        res.reasons.extend(leaks)
        res.checks.append(("no forbidden POSIX tokens", False))
    else:
        res.checks.append(("no forbidden POSIX tokens", True))
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repo root (default: two levels up from scripts/gates/)",
    )
    args = ap.parse_args(argv)
    return emit(check_no_posix_assumptions(args.repo.resolve()))


if __name__ == "__main__":
    raise SystemExit(main())
