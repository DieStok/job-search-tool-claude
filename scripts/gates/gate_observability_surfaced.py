#!/usr/bin/env python3
"""Gate: the final report surfaces captured behavior as evidence, not just prose.

The 2026-06-19 refinement makes observability-by-default first-class: an
implementation must capture its own behavior and the final report must SURFACE
that captured behavior back to the human as a plot / metric — answering "did it
actually work?" with evidence, not a vibe. This gate is the deterministic
backstop behind that requirement.

STRUCTURAL / shape-only (goal §R6). It checks two things and nothing semantic:

  1. a ``## Did it actually work? (evidence)`` heading exists (whole-token,
     against headings only);
  2. the report references at least one figure / metric artifact (an image,
     a data file, a markdown image, or a plot/figure/metric keyword).

It does NOT verify the figure is correct or corroborates the claim — that is the
separate-context reviewer's job.

Tiered enforcement (gatelib is binary, so the tier lives in the CLI): by default
it **warns and exits 0** (so it nudges at the ``standard`` tier without blocking);
with ``--strict`` (or ``--tier large`` / ``--tier agent-behavior``) it **blocks
and exits 1**. This lets the loop wire it as "warn @ standard / block @
large/agent-behavior". Pure-Python (stdlib only), GPU-free, dependency-free.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gatelib import GateResult, has_section_token, read_text, section_body  # noqa: E402

DEFAULT_HEADING = "did it actually work"
# Tiers that escalate the warn-default to a hard block.
STRICT_TIERS = {"large", "agent-behavior", "agent_behavior", "behavior"}

# A figure / metric artifact reference, hardened so bare keywords in NEGATIVE
# prose ("no figures at all") no longer match (MINOR-1). We accept any of:
#   (a) a markdown image  ![alt](path);
#   (b) an artifact file extension (.png/.csv/.json/...);
#   (c) the explicit reliability tokens pass^k / pass@k (self-evidently metric);
#   (d) a figure/plot/metric keyword that is ADJACENT to a number or path —
#       i.e. followed (after optional separators) by a digit or '/', as in
#       "column_f1 = 0.94", "figures/x.png", "metric: 0.9". A keyword sitting in
#       a prose sentence ("no figures at all here") is NOT followed by a number/
#       path and so does not match.
_ARTIFACT_RE = re.compile(
    r"!\[.*?\]\("  # (a) markdown image  ![alt](path)
    r"|\.(?:png|svg|jpe?g|pdf|gif|webp|csv|tsv|json|html)\b"  # (b) artifact file types
    r"|(?<![A-Za-z0-9])(?:pass\^k|pass@k)(?![A-Za-z0-9])"  # (c) reliability tokens
    r"|(?<![A-Za-z0-9])(?:figure|figures|fig|plot|chart|heatmap|histogram|"
    r"bar\s*chart|metric|metrics|f1|accuracy|precision|recall|kappa)"
    r"(?![A-Za-z0-9])[ \t:=~()|\-]*[\d/]",  # (d) keyword adjacent to a number/path
    re.IGNORECASE,
)


def _references_artifact(text: str) -> bool:
    return _ARTIFACT_RE.search(text) is not None


def check_observability(
    path: str | Path,
    heading: str = DEFAULT_HEADING,
    min_chars: int = 80,
) -> GateResult:
    res = GateResult(name="gate_observability_surfaced", passed=True)

    text = read_text(path)
    if not res.add("report exists", text is not None, f"no file at {path}"):
        return res
    text = text or ""

    res.add(
        f"has a '## {heading}? (evidence)' section",
        has_section_token(text, heading),
        f"no heading containing '{heading}' — the report does not surface "
        "captured-behavior evidence",
    )
    # Scope the artifact check to the EVIDENCE section body, so a '.json' / figure
    # mention elsewhere (e.g. the file-paths section) cannot satisfy a prose-only
    # evidence section (MAJOR-1).
    body = section_body(text, heading)
    res.add(
        "references >=1 figure/metric artifact",
        _references_artifact(body),
        f"no figure/metric artifact in the '## {heading}? (evidence)' section "
        "(an image, data file, or a number/path-adjacent plot/figure/metric "
        "mention) — evidence is prose-only",
    )
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report", help="path to the final report markdown")
    ap.add_argument("--heading", default=DEFAULT_HEADING, help="evidence heading keyword")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="block (exit 1) on failure instead of warning (for large/agent-behavior tiers)",
    )
    ap.add_argument(
        "--tier",
        default=None,
        help="routing tier; 'large'/'agent-behavior' imply --strict, others warn-only",
    )
    args = ap.parse_args(argv)

    strict = args.strict or (args.tier is not None and args.tier.lower() in STRICT_TIERS)
    result = check_observability(args.report, heading=args.heading)
    print(result.report())
    if result.passed:
        return 0
    if strict:
        return 1
    # warn-only: surface the gap loudly but do not block the loop.
    print(
        "  WARNING (non-blocking): observability evidence missing. This gate is "
        "warn-only at the current tier; re-run with --strict (or --tier large) to block."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
