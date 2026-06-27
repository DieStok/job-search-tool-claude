#!/usr/bin/env python3
"""Gate: the goal doc carries an ``## Evaluation Plan`` with a real scorer.

The 2026-06-19 refinement makes evaluation-crafting first-class: before any code
is written for a standard/large ask, the goal doc must answer "how will we know
EXACTLY that this works?" as a concrete, per-capability plan. This gate is the
cheap deterministic backstop behind that discipline.

STRUCTURAL / shape-only by design (goal §R6). It checks three things and NOTHING
semantic — it does not (and cannot) verify that every AC references a real scorer,
that the scorers are *good*, or that the bar is right. That cross-referencing is
the separate-context reviewer's job. The gate only proves the *shape* exists so a
loop cannot silently skip the eval-crafting step:

  1. an ``## Evaluation Plan`` heading exists (whole-token, against headings only);
  2. it is non-trivial (not a one-line stub);
  3. at least one **per-capability scorer-shaped line** is present — a list item
     or table row that names a scorer/metric/pass-fail check.

Mirrors the existing gates' conventions: pure-Python (stdlib only), GPU-free,
dependency-free, exits 0 (pass) / 1 (fail), prints a self-explanatory report.
The heading keyword, min-chars, and scorer keywords are CLI-overridable.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gatelib import GateResult, emit, has_section_token, read_text, section_body  # noqa: E402

DEFAULT_HEADING = "Evaluation Plan"

# Tokens that mark a line as describing a scorer/metric. Whole-token matched so a
# stray substring (e.g. "performance" containing "perf") does not count.
SCORER_KEYWORDS = [
    "scorer",
    "pass/fail",
    "pass-fail",
    "pass if",
    "binary",
    "exact match",
    "exact-match",
    "f1",
    "precision",
    "recall",
    "accuracy",
    "exit code",
    "exit-code",
    "grep",
    "kappa",
    "cohen",
    "pass^k",
    "pass@k",
    "metric",
    "rubric",
    "judge",
]
# A scorer-shaped line is a markdown LIST item (-, *, +, "1.") or a TABLE row
# (contains a pipe) — i.e. an enumerated item, not free prose — that also names a
# scorer keyword. This keeps the match structural without semantic parsing.
_LIST_RE = re.compile(r"^\s{0,8}(?:[-*+]\s+|\d+[.)]\s+)")
_KW_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(k).replace(r"\ ", r"[ \-]+") for k in SCORER_KEYWORDS) + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def _scorer_lines(text: str, keywords: list[str] | None = None) -> list[str]:
    kw_re = _KW_RE
    if keywords is not None:
        kw_re = re.compile(
            r"(?<![A-Za-z0-9])(?:"
            + "|".join(re.escape(k).replace(r"\ ", r"[ \-]+") for k in keywords)
            + r")(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
    out: list[str] = []
    for line in text.splitlines():
        is_item = bool(_LIST_RE.match(line)) or ("|" in line)
        if is_item and kw_re.search(line):
            out.append(line.strip())
    return out


def check_eval_plan(
    path: str | Path,
    heading: str = DEFAULT_HEADING,
    min_chars: int = 200,
    scorer_keywords: list[str] | None = None,
) -> GateResult:
    res = GateResult(name="gate_eval_plan_exists", passed=True)

    text = read_text(path)
    if not res.add("goal doc exists", text is not None, f"no file at {path}"):
        return res
    text = text or ""

    res.add(
        f"has an '## {heading}' heading",
        has_section_token(text, heading),
        f"no heading containing '{heading}' (the eval-crafting step was skipped)",
    )
    # Scope the content sub-checks to the Evaluation-Plan SECTION body (heading →
    # next same/higher heading), not the whole doc — otherwise an empty section
    # false-passes when a scorer word appears in an unrelated section (MAJOR-1).
    body = section_body(text, heading)
    res.add(
        "eval plan is non-trivial",
        len(body) >= min_chars,
        f"'## {heading}' section shorter than {min_chars} chars (looks like a stub)",
    )
    lines = _scorer_lines(body, scorer_keywords)
    res.add(
        "has >=1 per-capability scorer-shaped line",
        bool(lines),
        "no per-capability scorer-shaped line in the '## "
        f"{heading}' section (a list item / table row naming a "
        f"scorer/metric/pass-fail check); looked for {scorer_keywords or SCORER_KEYWORDS}",
    )
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("goal", help="path to the goal document markdown")
    ap.add_argument("--heading", default=DEFAULT_HEADING, help="eval-plan heading keyword")
    ap.add_argument("--min-chars", type=int, default=200, dest="min_chars")
    ap.add_argument(
        "--scorer-keyword",
        action="append",
        dest="scorer_keywords",
        help="scorer keyword (repeatable; overrides defaults)",
    )
    args = ap.parse_args(argv)
    return emit(
        check_eval_plan(
            args.goal,
            heading=args.heading,
            min_chars=args.min_chars,
            scorer_keywords=args.scorer_keywords,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
