"""Shared helpers for the /set-work-loops deterministic gate checkers.

These gates are intentionally pure-Python (stdlib only), GPU-free, and
dependency-free so the loop can run them as cheap, deterministic checks rather
than trusting a prompt-only "I reviewed it". Each gate exposes a ``check_*``
function returning a :class:`GateResult` plus a ``main()`` CLI that prints a
report and exits 0 (pass) / 1 (fail). The ECC analysis (docs/subagent_outputs/
2026-06-17_ecc_general_patterns_to_implement.md, item A1/anti-list) is explicit
that most ECC "gates" are prompt-only and that we must write the deterministic
enforcement ourselves — this module is that enforcement.

Hardened across two adversarial panels (2026-06-17). The first (D2/D5 draft
panel, reviewer #3) proved substring-matching false-passes: code fences are
stripped before heading detection, token matching is word-boundary-aware, and
clearing a blocking review verdict requires structural evidence, not a stray
keyword. The second (D5-final correctness review) proved further false-passes:
section-keyword matching against headings is now whole-word (``has_section_token``)
so "Screen resolution" no longer clears a CRITICAL and "Initialization" no longer
satisfies "initial", and setext (``Title\\n=====``) headings are recognized.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Heading line in markdown: one-or-more '#' then text.
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", re.MULTILINE)
# Setext h1/h2: a text line immediately followed by a line of only '=' or '-'.
# The '=' (h1) form is unambiguous. The '-' (h2) form is guarded to avoid
# matching horizontal rules / YAML front-matter delimiters / table separators:
# the title line must be non-empty, not itself an ATX heading, and not a table
# row (no pipe). Recognizing setext fixes the D5-final m3 false-fail on
# hand-authored ledgers that use Title/===== instead of '# Title'.
_SETEXT_RE = re.compile(
    r"^(?P<title>(?!\s{0,3}#)(?![ \t]*$)[^\n|]+?)[ \t]*\n[ \t]{0,3}(?:=+|-{2,})[ \t]*$",
    re.MULTILINE,
)
# Fenced code blocks, stripped before heading detection so a Python comment like
# `# workstream status` inside a fence is NOT a heading (panel reviewer #3, m3).
# Matches ```...``` and ~~~...~~~ fences (D5-final residual-risk: tilde fences).
_FENCE_RE = re.compile(r"(?:```|~~~).*?(?:```|~~~)", re.DOTALL)


@dataclass
class GateResult:
    """Outcome of a single deterministic gate.

    ``passed`` is the only thing the loop strictly needs; ``reasons`` and
    ``checks`` exist so a failure is self-explanatory (the ECC "show the gap,
    don't just name it" reporting rule).
    """

    name: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    checks: list[tuple[str, bool]] = field(default_factory=list)

    def add(self, label: str, ok: bool, reason: str | None = None) -> bool:
        self.checks.append((label, ok))
        if not ok:
            self.passed = False
            self.reasons.append(reason or label)
        return ok

    def report(self) -> str:
        head = f"[{'PASS' if self.passed else 'FAIL'}] {self.name}"
        lines = [head]
        for label, ok in self.checks:
            lines.append(f"  {'OK ' if ok else 'XX '} {label}")
        if not self.passed and self.reasons:
            lines.append("  reasons:")
            lines.extend(f"    - {r}" for r in self.reasons)
        return "\n".join(lines)


def read_text(path: str | Path) -> str | None:
    """Return file text, or ``None`` if the path is missing/unreadable."""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _strip_fences(text: str) -> str:
    return _FENCE_RE.sub("", text)


def headings(text: str) -> list[str]:
    """All markdown heading texts in ``text``, code fences removed.

    Recognizes both ATX (``# Title``) and setext (``Title\\n=====``) headings.
    """
    stripped = _strip_fences(text)
    atx = [m.strip() for m in _HEADING_RE.findall(stripped)]
    setext = [m.strip() for m in _SETEXT_RE.findall(stripped)]
    return atx + setext


def _iter_headings(stripped: str) -> list[tuple[int, int, int, str]]:
    """Return ``(start, end, level, heading_text)`` for every heading.

    ``start``/``end`` are character offsets of the heading LINE in ``stripped``
    (code-fence-removed) text; ``level`` is 1-6 (ATX ``#`` count, or 1/2 for
    setext ``=``/``-`` underlines). Sorted by position. Internal helper for
    :func:`section_body`.
    """
    out: list[tuple[int, int, int, str]] = []
    for m in _HEADING_RE.finditer(stripped):
        hashes = re.match(r"^\s{0,3}(#{1,6})", m.group(0))
        level = len(hashes.group(1)) if hashes else 6
        out.append((m.start(), m.end(), level, m.group(1).strip()))
    for m in _SETEXT_RE.finditer(stripped):
        level = 1 if "=" in m.group(0).rsplit("\n", 1)[-1] else 2
        out.append((m.start(), m.end(), level, m.group("title").strip()))
    out.sort(key=lambda r: r[0])
    return out


def section_body(text: str, keyword: str) -> str:
    """Return the body of the markdown section whose heading matches ``keyword``.

    The slice runs from the END of the matched heading line to the START of the
    next heading of the SAME-OR-HIGHER level (a ``## `` section ends at the next
    ``## `` or ``# ``; nested ``### `` headings are kept inside the body).
    Heading matching is whole-token (same robustness as :func:`has_section_token`)
    and code fences are stripped first, so a fenced fake ``## Heading`` neither
    matches nor terminates a section. Returns ``""`` if no heading matches.

    This is what lets the eval/observability gates scope their content sub-checks
    to the relevant SECTION rather than the whole document (fixes the MAJOR-1
    false-pass where an empty ``## Evaluation Plan`` / prose-only evidence section
    passed because a keyword appeared elsewhere in the doc).
    """
    stripped = _strip_fences(text)
    hs = _iter_headings(stripped)
    for i, (_start, end, level, htext) in enumerate(hs):
        if token_present(htext, keyword):
            body_end = len(stripped)
            for s2, _e2, l2, _t2 in hs[i + 1:]:
                if l2 <= level:
                    body_end = s2
                    break
            return stripped[end:body_end]
    return ""


def has_section(text: str, keyword: str) -> bool:
    """True if any heading contains ``keyword`` (case-insensitive substring).

    Loose substring match — use :func:`has_section_token` when a stray
    substring (e.g. "resolution" inside "Screen resolution") must not match.
    """
    kw = keyword.lower()
    return any(kw in h.lower() for h in headings(text))


def has_section_token(text: str, keyword: str) -> bool:
    """True if any heading contains ``keyword`` as a whole token.

    Whole-token (word-boundary) match, so "initial" matches a heading
    "What was initial ask" but NOT "Initialization steps", and "resolution"
    does NOT match "Screen resolution requirements". Multi-word keywords
    (``vs asked``) match across a single space or hyphen, mirroring
    :func:`token_present`. Fixes the D5-final correctness false-passes in
    gate_final_check (substring ``mentions``) and gate_work_reviewed
    (substring "resolution" clearing a CRITICAL).
    """
    return any(token_present(h, keyword) for h in headings(text))


# First alphabetic word of a heading, ignoring leading list markers / numbering
# (``## 3. Resolution`` -> "Resolution", ``- Resolution`` -> "Resolution").
_HEAD_LEAD_RE = re.compile(r"^[\W\d_]*([A-Za-z][\w-]*)")


def heading_starts_with(text: str, keyword: str) -> bool:
    """True if any heading's FIRST word equals ``keyword`` (case-insensitive).

    Stricter than :func:`has_section_token`: it anchors on the leading word, so a
    ``## Resolution`` (or ``## Resolution of findings``) section matches, while
    ``## Screen resolution requirements`` and ``## Conflict resolution`` do NOT
    (the word "resolution" appears, but not as the section's subject). This is the
    fix for the D5-final correctness review B-M1 — a stray "resolution" anywhere
    in a heading must not clear a CRITICAL review finding.
    """
    kw = keyword.lower()
    for h in headings(text):
        m = _HEAD_LEAD_RE.match(h)
        if m and m.group(1).lower() == kw:
            return True
    return False


def mentions(text: str, keyword: str) -> bool:
    """True if ``keyword`` appears anywhere in ``text`` (case-insensitive)."""
    return keyword.lower() in text.lower()


def token_present(text: str, token: str) -> bool:
    """Whole-token, case-insensitive match.

    Boundaries are non-alphanumeric, so ``D1`` matches ``D1`` / ``d1_review``
    but NOT ``D10`` or ``D11`` (panel reviewer #3, M2). A space in the token is
    treated as "space or hyphen" so ``NOT READY`` matches ``NOT-READY`` too, and
    crucially is matched as a *phrase* — it is no longer self-cleared by the bare
    substring ``READY`` (panel reviewer #3, C1/C2).
    """
    pat = re.escape(token).replace(r"\ ", r"[ \-]+")
    return re.search(rf"(?<![A-Za-z0-9]){pat}(?![A-Za-z0-9])", text, re.IGNORECASE) is not None


def emit(result: GateResult) -> int:
    """Print the report and return the process exit code (0 pass / 1 fail)."""
    print(result.report())
    return 0 if result.passed else 1
