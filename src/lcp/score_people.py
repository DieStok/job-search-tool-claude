"""D3 / AC-021 — Warmth scoring: who's worth a coffee and WHY.

This is the networking core.  For each person in staff.parquet it computes a
DETERMINISTIC warmth_score in [0,1] from six configurable weighted signals
(weights from rubric.yaml) and populates a `why[]` list with human-readable
explanations of WHICH signals fired.

Signals (all weights configurable via rubric.yaml warmth_weights):
  shared_school     — alumni overlap: person went to same university as operator
  shared_employer   — worked at the same company (past or present) as operator
  mutual_connection — person.contactable=True (proxy for 1st-degree connection)
  role_relevance    — person's skills/title overlap with operator's skills/seeking
  shared_affiliation— same city (from profile.affiliations.cities_lived) as operator
  recency_at_company— person recently joined the target company (start >= 2024, ongoing)

Output: data/people_to_meet.json — list of PersonToMeet sorted by warmth_score DESC,
then profile_url ASC for deterministic tiebreaking.  Entries below
rubric.warmth_min_score are dropped.  Top `people_scoring.top_n_people` are kept.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import Config
from .contracts import PersonToMeet, Staff
from .fetch_staff import read_staff_parquet
from .runlog import RunLogger

# Default weights (overridden by rubric.yaml)
_DEFAULT_WEIGHTS: dict[str, float] = {
    "shared_school": 0.30,
    "shared_employer": 0.30,
    "mutual_connection": 0.15,
    "role_relevance": 0.15,
    "shared_affiliation": 0.05,
    "recency_at_company": 0.05,
}


# ---------------------------------------------------------------------------
# Individual signal scorers
# ---------------------------------------------------------------------------


def _score_shared_school(person: Staff, profile: dict) -> tuple[float, str | None]:
    """Return (raw_signal, why_str) — 1.0 if any education school matches."""
    profile_schools = {
        e.get("school", "").lower().strip()
        for e in profile.get("education", [])
        if e.get("school")
    }
    for edu in person.education:
        if edu.school and edu.school.lower().strip() in profile_schools:
            return 1.0, f"shared school: {edu.school}"
    return 0.0, None


def _score_shared_employer(person: Staff, profile: dict) -> tuple[float, str | None]:
    """Return 1.0 if any experience matches a profile employer."""
    profile_companies = {
        e.get("company", "").lower().strip()
        for e in profile.get("employers", [])
        if e.get("company")
    }
    for exp in person.experiences:
        if exp.company and exp.company.lower().strip() in profile_companies:
            return 1.0, f"shared employer: {exp.company}"
    return 0.0, None


def _score_mutual_connection(person: Staff) -> tuple[float, str | None]:
    """Proxy: contactable=True means a 1st-degree connection."""
    if person.contactable:
        return 1.0, "mutual connection: 1st-degree connection"
    return 0.0, None


def _score_role_relevance(person: Staff, profile: dict) -> tuple[float, str | None]:
    """Fractional score: matched_profile_skills / total_profile_skills.

    Checks person.skills (exact item match) and person.title (substring match).
    """
    profile_skills = [s.lower().strip() for s in profile.get("skills", []) if s]
    if not profile_skills:
        return 0.0, None

    person_skills_lower = {s.lower().strip() for s in person.skills if s}
    title_lower = (person.title or "").lower()

    matched = [
        ps for ps in profile_skills
        if ps in person_skills_lower or ps in title_lower
    ]
    if not matched:
        return 0.0, None

    ratio = len(matched) / len(profile_skills)
    # Build a tidy comma-separated label of what matched
    label = ", ".join(sorted(set(matched)))
    return min(ratio, 1.0), f"role relevance: {label}"


def _score_shared_affiliation(person: Staff, profile: dict) -> tuple[float, str | None]:
    """1.0 if person.location contains any city from profile.affiliations.cities_lived."""
    affiliations = profile.get("affiliations", {})
    cities = [c.lower().strip() for c in affiliations.get("cities_lived", []) if c]
    if not cities or not person.location:
        return 0.0, None

    loc_lower = person.location.lower()
    for city in cities:
        if city in loc_lower:
            return 1.0, f"shared city: {city.title()}"
    return 0.0, None


def _score_recency_at_company(person: Staff) -> tuple[float, str | None]:
    """1.0 if the person recently joined the target company (start ≥ 2024, ongoing role).

    'ongoing' = years string ends with '-', contains 'present'/'current', or is a
    single recent year (e.g. '2025').
    """
    target = person.company.lower().strip()
    for exp in person.experiences:
        if not exp.company:
            continue
        comp = exp.company.lower().strip()
        if target not in comp and comp not in target:
            continue

        years = (exp.years or "").strip()
        if not years:
            continue

        # Check ongoing
        is_ongoing = (
            years.lower().endswith("-")
            or "present" in years.lower()
            or "current" in years.lower()
        )
        # Single-year format like "2025"
        if not is_ongoing and re.fullmatch(r"20\d{2}", years):
            is_ongoing = True

        # Extract start year (first 4-digit year)
        match = re.search(r"(20\d{2})", years)
        if match and is_ongoing and int(match.group(1)) >= 2024:
            return 1.0, f"recently joined: {exp.company}"
    return 0.0, None


# ---------------------------------------------------------------------------
# Per-person scoring
# ---------------------------------------------------------------------------


def _compute_warmth(
    person: Staff,
    profile: dict,
    weights: dict[str, float],
) -> tuple[float, list[str]]:
    """Compute (warmth_score, why[]) for a single person."""
    # Total weight (normalise in case operator has non-unit weights)
    total_w = sum(abs(w) for w in weights.values()) or 1.0

    score = 0.0
    why: list[str] = []

    scorers = [
        ("shared_school",      lambda: _score_shared_school(person, profile)),
        ("shared_employer",    lambda: _score_shared_employer(person, profile)),
        ("mutual_connection",  lambda: _score_mutual_connection(person)),
        ("role_relevance",     lambda: _score_role_relevance(person, profile)),
        ("shared_affiliation", lambda: _score_shared_affiliation(person, profile)),
        ("recency_at_company", lambda: _score_recency_at_company(person)),
    ]

    for signal_name, scorer_fn in scorers:
        w = weights.get(signal_name, _DEFAULT_WEIGHTS.get(signal_name, 0.0))
        if w <= 0:
            continue
        raw, reason = scorer_fn()
        if raw > 0 and reason:
            score += (w / total_w) * raw
            why.append(reason)

    return round(min(score, 1.0), 6), why


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def score_people(cfg: Config, logger: RunLogger) -> int:
    """Read staff.parquet, score warmth, write data/people_to_meet.json.

    Args:
        cfg:    Loaded pipeline config.
        logger: RunLogger for structured event output.

    Returns:
        Number of people written to people_to_meet.json.

    Raises:
        FileNotFoundError: If staff.parquet does not exist yet.
    """
    parquet_path = cfg.data_dir / "staff.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"staff.parquet not found at {parquet_path}. "
            "Run 'lcp staff fetch --company <name>' first."
        )

    profile = cfg.profile
    rubric = cfg.rubric
    weights: dict[str, float] = rubric.get("warmth_weights", _DEFAULT_WEIGHTS)
    warmth_min: float = float(rubric.get("warmth_min_score", 0.20))
    top_n: int = int(cfg.get("people_scoring.top_n_people", 15))

    staff_list = read_staff_parquet(parquet_path)

    scored: list[PersonToMeet] = []
    for person in staff_list:
        warmth_score, why = _compute_warmth(person, profile, weights)
        if warmth_score < warmth_min:
            continue
        scored.append(
            PersonToMeet(
                name=person.name,
                company=person.company,
                profile_url=person.profile_url,
                title=person.title,
                why=why,
                warmth_score=warmth_score,
                contact_status="new",
            )
        )

    # Deterministic sort: warmth DESC, then profile_url ASC (stable tiebreak)
    scored.sort(key=lambda p: (-p.warmth_score, p.profile_url))

    # Honour top_n
    scored = scored[:top_n]

    # Write output
    output_path = cfg.data_dir / "people_to_meet.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([p.model_dump() for p in scored], indent=2, default=str),
        encoding="utf-8",
    )

    logger.event(
        "score_people",
        count_out=len(scored),
        warmth_min=warmth_min,
        top_n=top_n,
        parquet=str(parquet_path),
    )
    return len(scored)
