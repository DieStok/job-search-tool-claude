#!/usr/bin/env python3
"""Gate: the comprehensive final report exists and has all required sections.

§13.4 of the goal doc mandates that every /set-work-loops run ends with ONE
comprehensive report covering six things. This gate checks each section is
present so the loop cannot declare "done" with a half-written report. The six
sections (whole-token-matched against headings, each CLI-overridable):

  1. what was asked initially (verbatim)        -> asked / initial ask
  2. what was actually done                      -> what was done / actually done
  3. multi-agent review outcomes + changes made  -> review
  4. drift from the initial instructions (diff)  -> drift / deviation
  5. overview of what was implemented            -> implement(ed) / overview
  6. important file paths to outputs             -> file paths / outputs / artifacts

Matching is whole-token against HEADINGS (``has_section_token``). Heading-required
(not free-text ``mentions``) after panel reviewer #3 M3 / reviewer #4 F4+F6: bare
keywords let unstructured prose pass all six checks. Whole-token after the
D5-final correctness review (same class as B-M1): substring matching let an
"Overview" heading satisfy the "review" section (section 5 masking section 3).
Section-5 carries explicit stems (``implemented``/``implementation``) because
whole-token "implement" would not match the inflected forms.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gatelib import GateResult, emit, has_section_token, read_text  # noqa: E402

# (label, [acceptable keywords]) — each section must appear as a HEADING that
# contains one of the keywords as a WHOLE TOKEN.
REQUIRED_SECTIONS: list[tuple[str, list[str]]] = [
    ("what was asked initially", ["asked", "initial ask", "verbatim"]),
    ("what was actually done", ["what was done", "actually done", "what we did"]),
    ("multi-agent review outcomes", ["review"]),
    ("drift / deviation diff", ["drift", "deviation", "scope change"]),
    (
        "overview of what was implemented",
        ["implement", "implemented", "implementation", "overview", "in practice"],
    ),
    ("important file paths to outputs", ["file path", "paths to", "artifact", "deliverable path"]),
]
# §13.5 umbrella add-on — only required when the run itself produced/tuned
# tooling (e.g. this very effort's skills). Opt-in via --umbrella (reviewer #4 F2).
UMBRELLA_SECTION: tuple[str, list[str]] = (
    "ECC findings + skill tuning (§13.5 umbrella)",
    ["ecc", "tuning", "tuned", "tooling", "skill itself"],
)


def check_report(
    path: str | Path,
    sections: list[tuple[str, list[str]]] | None = None,
    min_chars: int = 400,
    umbrella: bool = False,
) -> GateResult:
    sections = list(sections if sections is not None else REQUIRED_SECTIONS)
    if umbrella:
        sections = sections + [UMBRELLA_SECTION]
    res = GateResult(name="gate_report_written", passed=True)

    text = read_text(path)
    if not res.add("final report exists", text is not None, f"no report at {path}"):
        return res
    text = text or ""
    res.add(
        "report is non-trivial",
        len(text) >= min_chars,
        f"report shorter than {min_chars} chars (looks like a stub)",
    )
    for label, keywords in sections:
        ok = any(has_section_token(text, k) for k in keywords)
        res.add(
            f"section: {label}",
            ok,
            f"missing section heading for '{label}' (heading must contain one of {keywords})",
        )
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report", help="path to the comprehensive final report")
    ap.add_argument(
        "--umbrella",
        action="store_true",
        help="also require the §13.5 ECC-findings + skill-tuning section",
    )
    args = ap.parse_args(argv)
    return emit(check_report(args.report, umbrella=args.umbrella))


if __name__ == "__main__":
    raise SystemExit(main())
