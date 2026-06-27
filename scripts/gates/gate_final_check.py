#!/usr/bin/env python3
"""Gate: a final check of delivered work against the INITIAL ask exists.

The single most insidious failure of an autonomous loop is silent scope drift:
the loop optimizes for what it *decided* to build, not what was *asked*. ECC
anti-list and §13.3 both call this out. This gate requires an explicit
artifact that puts the original ask next to the delivered work and names the
gap. It is the cheap deterministic backstop behind the human GATE 2.

Requires the final-check artifact to contain, as explicit SECTION HEADINGS:
  * a reference to the INITIAL ask (asked / initial / request),
  * a reference to what was DELIVERED (delivered / done / implemented), and
  * an explicit comparison/gap section (drift / diff / gap / deviation /
    "vs asked" / unmet).
All keyword groups are CLI-overridable.

Hardened after the D5-final correctness review (B-M3): the old check fell
through to a free-text substring search (``mentions``), so vague prose with an
incidental "requested"/"done"/"diff" passed all three checks with no structure.
Matching is now whole-token against HEADINGS only (``has_section_token``), so
"Initialization" no longer satisfies "initial" and prose cannot pass the gate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gatelib import GateResult, emit, has_section_token, read_text  # noqa: E402

ASKED = ["asked", "initial", "request", "original ask"]
DELIVERED = ["delivered", "done", "implemented", "what was actually"]
GAP = ["drift", "diff", "gap", "deviation", "unmet", "vs asked", "vs. asked"]


def _any(text: str, keywords: list[str]) -> tuple[bool, str | None]:
    for k in keywords:
        if has_section_token(text, k):
            return True, k
    return False, None


def check_final_check(
    path: str | Path,
    asked: list[str] | None = None,
    delivered: list[str] | None = None,
    gap: list[str] | None = None,
    min_chars: int = 150,
) -> GateResult:
    asked = asked or ASKED
    delivered = delivered or DELIVERED
    gap = gap or GAP
    res = GateResult(name="gate_final_check", passed=True)

    text = read_text(path)
    if not res.add("final-check artifact exists", text is not None, f"no file at {path}"):
        return res
    text = text or ""

    # min_chars guard (panel reviewer #3, m1): a 3-line note must not pass.
    res.add(
        "artifact is non-trivial",
        len(text) >= min_chars,
        f"final-check shorter than {min_chars} chars (looks like a stub)",
    )
    ok_a, hit_a = _any(text, asked)
    res.add("references the INITIAL ask", ok_a, f"none of {asked} found")
    ok_d, hit_d = _any(text, delivered)
    res.add("references DELIVERED work", ok_d, f"none of {delivered} found")
    ok_g, hit_g = _any(text, gap)
    res.add(
        "has an explicit asked-vs-done comparison",
        ok_g,
        f"no explicit asked-vs-done comparison (drift/gap/diff) section; looked for {gap}",
    )
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("artifact", help="path to the final-check markdown")
    ap.add_argument("--asked", action="append", dest="asked")
    ap.add_argument("--delivered", action="append", dest="delivered")
    ap.add_argument("--gap", action="append", dest="gap")
    args = ap.parse_args(argv)
    return emit(
        check_final_check(
            args.artifact, asked=args.asked, delivered=args.delivered, gap=args.gap
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
