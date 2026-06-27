#!/usr/bin/env python3
"""Gate: a central ledger was created and has the required structure.

Why this is a deterministic gate, not a vibe-check: in the 2026-06-17
actuation-parity run the ledger (docs/2026-06-17_actuation-parity_LEDGER.md)
was the single source of truth across ~17 loop wakes and several agent
hand-offs. SendMessage was unavailable, so a *running* agent could not be
steered — the ledger + clear final reports were the ONLY coordination channel.
A loop that never wrote a structured ledger has no recoverable state. This gate
fails loud if the ledger is missing a workstream table, a wake log, or a link
back to its goal document.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gatelib import GateResult, emit, has_section, read_text  # noqa: E402

DEFAULT_SECTIONS = ["workstream status", "wake log"]
# A real goal/plan reference: a single line where a goal/plan/spec/aims/objective
# word co-occurs (before) an .md filename — whether as a markdown link
# `[goal](docs/x_goal.md)` or as prose `spec is docs/x_goal.md`. Hardened twice:
# - panel reviewer #3 M4: the old "(goal|plan) anywhere AND .md anywhere" was
#   gameable by an unrelated readme.md mention and false-failed on *_aims.md docs.
# - D5-final correctness review B-C1: the separate "any markdown link to any .md"
#   branch let `[workflow](figures/workflow.md)` (no goal vocab) clear the gate.
#   That branch is removed — a goal/plan reference now ALWAYS requires the vocab
#   word on the same line as the .md (which markdown links satisfy naturally).
_GOALREF_LINE_RE = re.compile(r"(goal|plan|spec|aims|objective)\w*[^\n]*?\.md", re.IGNORECASE)


def _references_goal_doc(text: str) -> bool:
    return any(_GOALREF_LINE_RE.search(line) for line in text.splitlines())


def check_ledger(
    path: str | Path,
    required_sections: list[str] | None = None,
    min_chars: int = 200,
) -> GateResult:
    sections = required_sections if required_sections is not None else DEFAULT_SECTIONS
    res = GateResult(name="gate_ledger_exists", passed=True)

    text = read_text(path)
    if res.add("ledger file exists", text is not None, f"no ledger at {path}"):
        res.add(
            "ledger is non-trivial",
            len(text or "") >= min_chars,
            f"ledger shorter than {min_chars} chars (looks like a stub)",
        )
        for sec in sections:
            res.add(
                f"has '{sec}' section",
                has_section(text or "", sec),
                f"missing required heading containing '{sec}'",
            )
        # A ledger must point back at the goal/plan doc it tracks.
        res.add(
            "references a goal/plan document",
            _references_goal_doc(text or ""),
            "ledger must reference its goal/plan doc on one line (e.g. 'spec is docs/..._goal.md')",
        )
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger", help="path to the markdown ledger")
    ap.add_argument(
        "--section",
        action="append",
        dest="sections",
        help="required heading keyword (repeatable; overrides defaults)",
    )
    args = ap.parse_args(argv)
    return emit(check_ledger(args.ledger, required_sections=args.sections))


if __name__ == "__main__":
    raise SystemExit(main())
