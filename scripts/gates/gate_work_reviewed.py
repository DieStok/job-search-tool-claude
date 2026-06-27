#!/usr/bin/env python3
"""Gate: every deliverable has a separate-context review with findings resolved.

ECC pattern #3 (separate-context reviewer) + our own CE Phase 4: the reviewer
must run in a *fresh* context and its findings must be folded before a
deliverable is "done". In the 2026-06-17 run the D2 skill's own panel verdict
was FIX-FIRST (6/10) and found a CRITICAL (C1: renderers never wired) — shipping
on the author's self-assessment would have shipped a skill that was silently
inert on half its checks. This gate is deterministic enforcement of "reviewed +
resolved": for each named deliverable it requires at least one review artifact,
and that artifact must not carry an unresolved blocking verdict.

Hardened after the D5 draft panel (reviewer #3, C1/C2/M1/M2):
  * Deliverable<->review attribution uses whole-token matching (``D1`` no longer
    matches ``D10`` or a passing mention of ``D1`` in a D3 review); a body match
    must sit on a line that also names "review"/"deliverable".
  * Blocking tokens are matched as whole phrases (``NOT READY`` is no longer
    self-cleared by the substring ``READY``; ``UNRESOLVED`` no longer by
    ``RESOLVED``).
  * A blocking verdict is cleared ONLY by structural evidence — a ``Resolution``
    heading, or a *verdict line* that names a clearing token and is not itself a
    blocking verdict. A stray "we'll pass this on" no longer clears a CRITICAL.

Hardened again after the D5-final correctness review (B-M1/B-M2/B-M4):
  * The ``Resolution`` heading check is whole-token (``has_section_token``) so a
    heading like "Screen resolution requirements" no longer clears a CRITICAL.
  * Verdict-line clearing now consults the LAST verdict line, so an early
    "Verdict: PASS (initial)" can no longer mask a later "Final verdict:
    FIX-FIRST".
  * The review-context filter is whole-token, so "preview the D1 results" no
    longer counts a file as a review OF D1 ("review" inside "preview").
The token lists are CLI-overridable so the gate adapts to a team's vocabulary.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gatelib import (  # noqa: E402
    GateResult,
    emit,
    heading_starts_with,
    read_text,
    token_present,
)

DEFAULT_BLOCKING = ["CRITICAL", "FIX-FIRST", "NOT READY", "BLOCKER", "UNRESOLVED"]
DEFAULT_CLEARING = ["RESOLVED", "READY", "APPROVE", "APPROVED", "PASS", "SHIP IT"]
# A "verdict line" is where a real review states its disposition.
_VERDICT_LINE_RE = re.compile(r"^\s*[*_>#\-\d.]*\s*(final\s+)?verdict\b", re.IGNORECASE)
# Lines that name the deliverable as a review subject (not a passing mention).
_REVIEW_CONTEXT = ("review", "deliverable", "workstream")


def _review_files(reviews_dir: Path, deliverable: str) -> list[Path]:
    """Files that are plausibly a review *of* ``deliverable``.

    Whole-token match on the filename, OR a body line that names the deliverable
    AND is a review-context line (contains review/deliverable/workstream). This
    stops a D3 review that mentions D1 in passing from counting as a D1 review,
    and stops ``d10_review.md`` from matching deliverable ``D1``.
    """
    out: list[Path] = []
    if not reviews_dir.is_dir():
        return out
    for p in sorted(reviews_dir.glob("*.md")):
        if token_present(p.name, deliverable):
            out.append(p)
            continue
        text = read_text(p) or ""
        for line in text.splitlines():
            if token_present(line, deliverable) and any(
                token_present(line, c) for c in _REVIEW_CONTEXT
            ):
                out.append(p)
                break
    return out


def _is_resolved(text: str, blocking: list[str], clearing: list[str]) -> tuple[bool, str]:
    blocked = [b for b in blocking if token_present(text, b)]
    if not blocked:
        return True, "no blocking findings"
    if heading_starts_with(text, "resolution"):
        return True, f"blocking {blocked} present but a Resolution section exists"
    # The disposition of a review is its LAST verdict line. An early
    # "Verdict: PASS (initial)" must NOT mask a later "Final verdict: FIX-FIRST"
    # (D5-final correctness review B-M2).
    verdict_lines = [ln for ln in text.splitlines() if _VERDICT_LINE_RE.match(ln)]
    if verdict_lines:
        last = verdict_lines[-1]
        last_blocking = any(token_present(last, b) for b in blocking)
        last_clearing = any(token_present(last, c) for c in clearing)
        if last_clearing and not last_blocking:
            return True, f"blocking {blocked} present but cleared by verdict: {last.strip()[:60]!r}"
    return False, f"unresolved blocking finding(s): {blocked}"


def check_work_reviewed(
    reviews_dir: str | Path,
    deliverables: list[str],
    blocking: list[str] | None = None,
    clearing: list[str] | None = None,
) -> GateResult:
    blocking = blocking or DEFAULT_BLOCKING
    clearing = clearing or DEFAULT_CLEARING
    rdir = Path(reviews_dir)
    res = GateResult(name="gate_work_reviewed", passed=True)

    if not deliverables:
        res.add("deliverables provided", False, "no deliverables passed to the gate")
        return res

    for d in deliverables:
        files = _review_files(rdir, d)
        if not res.add(
            f"deliverable '{d}' has a review artifact",
            bool(files),
            f"no review .md in {rdir} is a review of '{d}'",
        ):
            continue
        verdicts = [_is_resolved(read_text(f) or "", blocking, clearing) for f in files]
        ok = any(v[0] for v in verdicts)
        detail = "; ".join(f"{f.name}: {v[1]}" for f, v in zip(files, verdicts))
        res.add(
            f"deliverable '{d}' review findings resolved",
            ok,
            f"all reviews unresolved -> {detail}",
        )
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("reviews_dir", help="directory of review .md artifacts")
    ap.add_argument(
        "--deliverable",
        action="append",
        dest="deliverables",
        required=True,
        help="deliverable id that must have a resolved review (repeatable)",
    )
    ap.add_argument("--blocking", action="append", dest="blocking")
    ap.add_argument("--clearing", action="append", dest="clearing")
    args = ap.parse_args(argv)
    return emit(
        check_work_reviewed(
            args.reviews_dir,
            args.deliverables,
            blocking=args.blocking,
            clearing=args.clearing,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
