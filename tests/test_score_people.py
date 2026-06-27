"""D3 / AC-021 — score_people: warmth scoring, ranked why[], deterministic.

Golden fixtures:
  eval/golden/staff_sample.json  → 3 staff at TechCorp
  eval/golden/profile_sample.yaml → Test User (UvA alumni, ex-DataCo BV, Amsterdam)

Expected scoring (warmth_weights from rubric.example.yaml):
  Alice van Dam : 0.30 (school) + 0.30 (employer) + 0.15 (connection)
                + ~0.10 (role: python+data_engineering / 3 skills) + 0.05 (city) + 0.05 (recency) = 0.95
  Bob de Jong   : 0.30 (school) + 0.05 (role: python/3) + 0.05 (city: Utrecht) + 0.05 (recency) = 0.45
  Carol Jansen  : ~0.10 (role: ml+data_eng / 3) → below warmth_min_score=0.20 → DROPPED

Alice is first, Bob is second, Carol is absent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
import pytest

from lcp.config import load_config
from lcp.contracts import Education, Experience, PersonToMeet, Staff
from lcp.runlog import RunLogger

REPO = Path(__file__).resolve().parents[1]
GOLDEN_STAFF = json.loads((REPO / "eval/golden/staff_sample.json").read_text())
GOLDEN_PROFILE = yaml.safe_load((REPO / "eval/golden/profile_sample.yaml").read_text())


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write_staff_parquet(staff_list: list[Staff], path: Path) -> None:
    """Write a staff.parquet from a list of Staff objects (mirrors fetch_staff format)."""
    from lcp.fetch_staff import write_staff_parquet
    write_staff_parquet(staff_list, path)


def _load_golden_staff() -> list[Staff]:
    return [Staff.model_validate(r) for r in GOLDEN_STAFF]


def _cfg(tmp_path: Path, top_n: int = 15) -> Any:
    cfg = load_config(REPO / "config/config.example.yaml")
    cfg.raw.setdefault("people_scoring", {})
    cfg.raw["people_scoring"]["top_n_people"] = top_n
    cfg.raw["meta"]["data_dir"] = str(tmp_path / "data")
    cfg.raw["state"]["sqlite_path"] = str(tmp_path / "state.sqlite")
    cfg.raw["observability"]["run_log_dir"] = str(tmp_path / "runs")
    # Inject the golden profile
    cfg.profile.clear()
    cfg.profile.update(GOLDEN_PROFILE)
    return cfg


def _run_scoring(tmp_path: Path, cfg: Any, staff: list[Staff] | None = None) -> list[PersonToMeet]:
    """Write parquet, run score_people, return parsed people_to_meet.json."""
    if staff is None:
        staff = _load_golden_staff()
    data_dir = Path(cfg.raw["meta"]["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_staff_parquet(staff, data_dir / "staff.parquet")

    logger = RunLogger(tmp_path / "runs")
    from lcp.score_people import score_people
    score_people(cfg, logger)

    people_json = data_dir / "people_to_meet.json"
    assert people_json.exists(), "people_to_meet.json not written"
    raw = json.loads(people_json.read_text())
    return [PersonToMeet.model_validate(r) for r in raw]


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_golden_ranking_alice_first_bob_second(tmp_path):
    """Golden input: Alice > Bob; Carol dropped below warmth_min_score."""
    cfg = _cfg(tmp_path)
    people = _run_scoring(tmp_path, cfg)

    names = [p.name for p in people]
    assert "Alice van Dam" in names, "Alice must be in output"
    assert "Bob de Jong" in names, "Bob must be in output"
    assert "Carol Jansen" not in names, "Carol is below threshold — must be dropped"

    alice_idx = names.index("Alice van Dam")
    bob_idx = names.index("Bob de Jong")
    assert alice_idx < bob_idx, "Alice must rank higher than Bob"


def test_alice_score_higher_than_bob(tmp_path):
    """Alice's warmth_score must be numerically higher than Bob's."""
    cfg = _cfg(tmp_path)
    people = _run_scoring(tmp_path, cfg)

    scores = {p.name: p.warmth_score for p in people}
    assert scores["Alice van Dam"] > scores["Bob de Jong"]


def test_all_scores_in_range(tmp_path):
    """Every warmth_score must be in [0, 1]."""
    cfg = _cfg(tmp_path)
    people = _run_scoring(tmp_path, cfg)
    for p in people:
        assert 0.0 <= p.warmth_score <= 1.0, f"{p.name} score {p.warmth_score} out of range"


def test_all_people_have_non_empty_why(tmp_path):
    """Every person in output must have a non-empty why[] (AC-021)."""
    cfg = _cfg(tmp_path)
    people = _run_scoring(tmp_path, cfg)
    assert people, "Output must not be empty"
    for p in people:
        assert p.why, f"{p.name} has empty why[] — violates AC-021"


def test_top_person_why_cites_shared_school(tmp_path):
    """Alice's why[] must cite the shared school (University of Amsterdam)."""
    cfg = _cfg(tmp_path)
    people = _run_scoring(tmp_path, cfg)

    alice = next(p for p in people if p.name == "Alice van Dam")
    uva_cited = any("university of amsterdam" in w.lower() for w in alice.why)
    assert uva_cited, f"Alice why={alice.why!r} does not cite UvA"


def test_top_person_why_cites_shared_employer(tmp_path):
    """Alice's why[] must cite the shared employer (DataCo BV)."""
    cfg = _cfg(tmp_path)
    people = _run_scoring(tmp_path, cfg)

    alice = next(p for p in people if p.name == "Alice van Dam")
    employer_cited = any("dataco" in w.lower() for w in alice.why)
    assert employer_cited, f"Alice why={alice.why!r} does not cite DataCo BV"


def test_bob_why_cites_shared_school(tmp_path):
    """Bob's why[] must cite shared school (University of Amsterdam) — his primary signal."""
    cfg = _cfg(tmp_path)
    people = _run_scoring(tmp_path, cfg)

    bob = next(p for p in people if p.name == "Bob de Jong")
    uva_cited = any("university of amsterdam" in w.lower() for w in bob.why)
    assert uva_cited, f"Bob why={bob.why!r} does not cite UvA"


def test_below_threshold_dropped(tmp_path):
    """Carol scores below warmth_min_score=0.20 and must not appear."""
    cfg = _cfg(tmp_path)
    people = _run_scoring(tmp_path, cfg)
    assert all(p.name != "Carol Jansen" for p in people)


def test_deterministic_stable_ordering(tmp_path):
    """Running score_people twice on the same input produces identical order."""
    cfg = _cfg(tmp_path)
    people1 = _run_scoring(tmp_path, cfg)

    # Second run overwrites the parquet with the same data
    cfg2 = _cfg(tmp_path)
    people2 = _run_scoring(tmp_path, cfg2)

    assert [p.profile_url for p in people1] == [p.profile_url for p in people2], \
        "Ordering is not deterministic"


def test_top_n_respected(tmp_path):
    """top_n_people config is honored."""
    cfg = _cfg(tmp_path, top_n=1)  # only 1 person
    people = _run_scoring(tmp_path, cfg)
    assert len(people) <= 1


def test_runlog_event_emitted(tmp_path):
    """Run-log must contain a score_people event with count_out."""
    import json as _json

    cfg = _cfg(tmp_path)
    staff = _load_golden_staff()
    data_dir = Path(cfg.raw["meta"]["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)
    _write_staff_parquet(staff, data_dir / "staff.parquet")

    logger = RunLogger(tmp_path / "runs")
    from lcp.score_people import score_people
    score_people(cfg, logger)

    events = [
        _json.loads(line)
        for line in logger.path.read_text().splitlines()
        if line.strip()
    ]
    stage_events = [e for e in events if e.get("stage") == "score_people"]
    assert stage_events, "score_people event missing from run-log"
    assert isinstance(stage_events[-1].get("count_out"), int)


def test_weights_come_from_config(tmp_path):
    """Zero-out shared_school weight → Alice must lose the school bonus."""
    cfg = _cfg(tmp_path)
    # Override warmth_weights: school = 0 so Alice loses the school+employer edge vs Carol
    cfg.rubric["warmth_weights"] = {
        "shared_school": 0.0,
        "shared_employer": 0.0,
        "mutual_connection": 0.15,
        "role_relevance": 0.60,
        "shared_affiliation": 0.05,
        "recency_at_company": 0.20,
    }
    # Also lower the min threshold so Carol can appear
    cfg.rubric["warmth_min_score"] = 0.05

    people = _run_scoring(tmp_path, cfg)
    # Carol has machine_learning + data_engineering (2/3 skills) → role_relevance = 0.60*(2/3) = 0.40
    # Carol should now appear
    names = [p.name for p in people]
    assert "Carol Jansen" in names, "Carol must appear when threshold is lowered and weights rebalanced"
