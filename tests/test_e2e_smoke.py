"""D6 — end-to-end smoke test on golden data (tmp_path only; NEVER touches repo data/).

Pipeline exercised end-to-end with mocked network calls:
  fetch_jobs (mocked JobSpy) → rank_jobs → fetch_staff (mocked StaffSpy) →
  score_people → impl_draft_outreach → funnel metric

All artifacts land in pytest's tmp_path. The repo's data/ directory is NEVER written.

Shape notes:
  - jobspy raw DataFrame columns: id, site, job_url, title, company, company_url, location,
    is_remote, min_amount, max_amount, currency, date_posted, description, job_level,
    company_industry  (fetch_jobs._normalize_row maps these to the JobPost contract)
  - staffspy raw DataFrame columns: name, headline, profile_link, location, skills,
    experiences, educations, email, is_connection  (fetch_staff._df_row_to_staff maps these)
  - Staff parquet is written/read via fetch_staff.write_staff_parquet / read_staff_parquet
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
GOLDEN_JOBS: list[dict] = json.loads(
    (REPO / "eval/golden/jobs_sample.json").read_text(encoding="utf-8")
)
GOLDEN_STAFF: list[dict] = json.loads(
    (REPO / "eval/golden/staff_sample.json").read_text(encoding="utf-8")
)
GOLDEN_PROFILE: dict = yaml.safe_load(
    (REPO / "eval/golden/profile_sample.yaml").read_text(encoding="utf-8")
)
REFERENCE_DATE = date(2026, 6, 27)


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------


def _make_cfg(tmp_path: Path):
    """Return a Config directed entirely at tmp_path.

    All three path properties (data_dir, sqlite_path, run_log_dir) are
    overridden to absolute tmp paths so paths.resolve returns them as-is,
    guaranteeing no write ever touches the repo's data/ directory.
    """
    from lcp.config import load_config

    cfg = load_config(REPO / "config/config.example.yaml")

    # Absolute paths → paths.resolve returns them unchanged
    cfg.raw["meta"]["data_dir"] = str(tmp_path / "data")
    cfg.raw["state"]["sqlite_path"] = str(tmp_path / "state.sqlite")
    cfg.raw["observability"]["run_log_dir"] = str(tmp_path / "runs")

    # Inject the golden profile (warmth scoring uses it)
    cfg.profile.clear()
    cfg.profile.update(GOLDEN_PROFILE)

    # Minimal job config so the mock is called once per test
    cfg.raw.setdefault("jobs", {})
    cfg.raw["jobs"]["search_terms"] = ["data engineer"]
    cfg.raw["jobs"]["site_names"] = ["linkedin"]
    cfg.raw["jobs"].setdefault("adzuna", {})
    cfg.raw["jobs"]["adzuna"]["enabled"] = False

    # StaffSpy settings (mock replaces the network; delay=0 skips sleep)
    cfg.raw.setdefault("people", {})
    cfg.raw["people"]["provider"] = "staffspy"
    cfg.raw["people"].setdefault("staffspy", {})
    cfg.raw["people"]["staffspy"]["max_profiles_per_company_per_day"] = 75
    cfg.raw["people"]["staffspy"]["inter_request_delay_sec"] = 0
    cfg.raw["people"]["staffspy"]["session_file"] = str(tmp_path / "session.pkl")
    cfg.raw["people"]["staffspy"]["captcha_solver"] = "none"

    cfg.raw.setdefault("people_scoring", {})
    cfg.raw["people_scoring"]["top_n_people"] = 15

    return cfg


# ---------------------------------------------------------------------------
# Mock builders
# ---------------------------------------------------------------------------


def _jobspy_df_from_golden() -> pd.DataFrame:
    """Convert jobs_sample.json (JobPost format) → JobSpy raw DataFrame format.

    fetch_jobs._normalize_row expects columns: job_url, id, title, company,
    company_url, location, is_remote, min_amount, max_amount, currency,
    date_posted, description, job_level, company_industry, site.
    """
    rows = []
    for job in GOLDEN_JOBS:
        # Extract board-specific id from "source:board_id" natural key
        parts = job["job_id"].split(":", 1)
        board_id = parts[1] if len(parts) == 2 else job["job_id"]
        rows.append(
            {
                "id": board_id,
                "site": job["source"],
                "job_url": job["job_url"],
                "title": job["title"],
                "company": job["company"],
                "company_url": job.get("company_url"),
                "location": job.get("location"),
                "is_remote": job.get("remote"),
                "min_amount": job.get("salary_min"),
                "max_amount": job.get("salary_max"),
                "currency": job.get("salary_currency"),
                "date_posted": (
                    pd.Timestamp(job["date_posted"]) if job.get("date_posted") else None
                ),
                "description": job.get("description"),
                "job_level": job.get("job_level"),
                "company_industry": job.get("company_industry"),
            }
        )
    return pd.DataFrame(rows)


def _staffspy_mock_module(staff_json: list[dict]) -> MagicMock:
    """Build a mock staffspy module returning the golden staff as a DataFrame.

    fetch_staff._df_row_to_staff maps: name, headline→title, profile_link→profile_url,
    location, skills (list), experiences (list of dicts with company/title/date_range),
    educations (list of dicts with school/degree_name/field_of_study/date_range),
    email, is_connection→contactable.
    """
    df_rows = []
    for r in staff_json:
        df_rows.append(
            {
                "name": r["name"],
                "headline": r["title"],
                "profile_link": r["profile_url"],
                "location": r["location"],
                "skills": r["skills"],
                "experiences": [
                    {
                        "company": e["company"],
                        "title": e.get("title"),
                        "date_range": e.get("years", ""),
                    }
                    for e in r["experiences"]
                ],
                "educations": [
                    {
                        "school": e["school"],
                        "degree_name": e.get("degree"),
                        "field_of_study": e.get("field"),
                        "date_range": e.get("years"),
                    }
                    for e in r["education"]
                ],
                "email": r.get("email"),
                "is_connection": r.get("contactable", False),
            }
        )
    df = pd.DataFrame(df_rows)
    mock_session = MagicMock()
    mock_session.scrape_staff.return_value = df
    mock_mod = MagicMock()
    mock_mod.LinkedInSession.return_value = mock_session
    return mock_mod


# ---------------------------------------------------------------------------
# Full pipeline end-to-end test
# ---------------------------------------------------------------------------


class TestE2ESmokePipeline:
    """Full deterministic pipeline on golden data; all artifacts in tmp_path."""

    def test_full_funnel_non_zero(self, tmp_path: Path) -> None:
        """Step through the complete pipeline and assert every funnel stage > 0.

        This is the core 'did it actually work?' evidence required by GOAL §7.
        """
        from lcp import runlog
        from lcp.fetch_jobs import fetch_jobs
        from lcp.fetch_staff import fetch_staff
        from lcp.mcp_server import impl_draft_outreach
        from lcp.rank_jobs import rank_jobs
        from lcp.score_people import score_people

        cfg = _make_cfg(tmp_path)
        data_dir = cfg.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)

        # Single logger → all stage events land in one .jsonl so funnel sees them all.
        logger = runlog.RunLogger(cfg.run_log_dir)

        # ---- Step 1: fetch_jobs (mocked JobSpy) --------------------------------
        jobspy_df = _jobspy_df_from_golden()
        # _scrape_fn DI: ignores all kwargs, returns all golden jobs once.
        n_fetched = fetch_jobs(cfg, logger, _scrape_fn=lambda **_kw: jobspy_df)

        assert n_fetched > 0, "fetch_jobs returned 0 new jobs"
        assert (data_dir / "jobs.parquet").exists(), "jobs.parquet not written"
        assert (data_dir / "jobs.csv").exists(), "jobs.csv not written"

        # ---- Step 2: rank_jobs -------------------------------------------------
        n_shortlisted = rank_jobs(cfg, logger, _today=REFERENCE_DATE)

        assert n_shortlisted > 0, "rank_jobs produced empty shortlist"
        shortlist_path = data_dir / "shortlist.json"
        assert shortlist_path.exists(), "shortlist.json not written"
        shortlist = json.loads(shortlist_path.read_text(encoding="utf-8"))
        assert len(shortlist) == n_shortlisted, "shortlist.json entry count mismatch"
        for entry in shortlist:
            assert 0.0 <= entry["score"] <= 1.0, f"score out of [0,1]: {entry}"
            assert entry.get("reasons"), f"entry {entry['job_id']} has no cited reasons"

        # ---- Step 3: fetch_staff (mocked StaffSpy) ----------------------------
        mock_ss = _staffspy_mock_module(GOLDEN_STAFF)
        with patch.dict(sys.modules, {"staffspy": mock_ss}):
            n_staff = fetch_staff(cfg, ["TechCorp"], logger)

        assert n_staff > 0, "fetch_staff returned 0 staff"
        assert (data_dir / "staff.parquet").exists(), "staff.parquet not written"

        # ---- Step 4: score_people ---------------------------------------------
        n_people = score_people(cfg, logger)

        assert n_people > 0, "score_people returned 0 people to meet"
        people_path = data_dir / "people_to_meet.json"
        assert people_path.exists(), "people_to_meet.json not written"
        people = json.loads(people_path.read_text(encoding="utf-8"))
        assert len(people) == n_people, "people_to_meet.json count mismatch"
        for p in people:
            assert p.get("why"), f"person {p['name']} has empty why[] (AC-021)"
            assert p.get("warmth_score", 0) > 0, f"person {p['name']} has zero warmth"

        # ---- Step 5: draft outreach -------------------------------------------
        top = people[0]
        draft = impl_draft_outreach(cfg, logger, top["profile_url"])

        assert draft.get("status") != "not_found", (
            f"top person not in people_to_meet.json: {draft}"
        )
        assert draft.get("sent") is False, "OutreachDraft.sent must always be False (draft-only)"
        signal = draft.get("warmth_signal_used", "")
        assert signal, "draft missing warmth_signal_used"
        body = draft.get("body", "")
        assert len(body) > 20, "draft body is suspiciously short"
        # Signal phrase must appear in the body (curiosity framing, not generic)
        signal_phrase = signal.split(":", 1)[1].strip() if ":" in signal else signal
        assert signal_phrase.lower() in body.lower(), (
            f"draft body does not reference the warmth signal phrase '{signal_phrase}'. "
            f"Body was: {body!r}"
        )

        # ---- Step 6: funnel coherence (the §7 evidence) -----------------------
        f = runlog.funnel(cfg.run_log_dir)
        assert f["jobs_fetched"] > 0, f"funnel.jobs_fetched == 0; full funnel: {f}"
        assert f["shortlisted"] > 0, f"funnel.shortlisted == 0; full funnel: {f}"
        assert f["people"] > 0, f"funnel.people == 0; full funnel: {f}"
        assert f["people_to_meet"] > 0, f"funnel.people_to_meet == 0; full funnel: {f}"
        assert f["drafts"] > 0, f"funnel.drafts == 0; full funnel: {f}"

    def test_shortlist_is_deterministic(self, tmp_path: Path) -> None:
        """rank_jobs on identical input produces the same order on two consecutive runs."""
        from lcp import runlog
        from lcp.fetch_jobs import fetch_jobs
        from lcp.rank_jobs import rank_jobs

        cfg = _make_cfg(tmp_path)
        logger = runlog.RunLogger(cfg.run_log_dir)
        jobspy_df = _jobspy_df_from_golden()
        fetch_jobs(cfg, logger, _scrape_fn=lambda **_kw: jobspy_df)

        rank_jobs(cfg, logger, _today=REFERENCE_DATE)
        first_run = json.loads((cfg.data_dir / "shortlist.json").read_text(encoding="utf-8"))

        rank_jobs(cfg, logger, _today=REFERENCE_DATE)
        second_run = json.loads((cfg.data_dir / "shortlist.json").read_text(encoding="utf-8"))

        assert [e["job_id"] for e in first_run] == [e["job_id"] for e in second_run], (
            "rank_jobs is non-deterministic (different order on second run)"
        )

    def test_excluded_job_not_in_shortlist(self, tmp_path: Path) -> None:
        """'Sales Manager' (indeed:2002) is dropped by excluded_titles = ['sales']."""
        from lcp import runlog
        from lcp.fetch_jobs import fetch_jobs
        from lcp.rank_jobs import rank_jobs

        cfg = _make_cfg(tmp_path)
        logger = runlog.RunLogger(cfg.run_log_dir)
        fetch_jobs(cfg, logger, _scrape_fn=lambda **_kw: _jobspy_df_from_golden())
        rank_jobs(cfg, logger, _today=REFERENCE_DATE)

        shortlist = json.loads((cfg.data_dir / "shortlist.json").read_text(encoding="utf-8"))
        ids = {e["job_id"] for e in shortlist}
        assert "indeed:2002" not in ids, (
            "'Sales Manager' should be excluded by rubric excluded_titles"
        )

    def test_people_to_meet_have_cited_reasons(self, tmp_path: Path) -> None:
        """Every entry in people_to_meet.json must cite >= 1 warmth reason (AC-021)."""
        from lcp import runlog
        from lcp.contracts import Staff
        from lcp.fetch_staff import write_staff_parquet
        from lcp.score_people import score_people

        cfg = _make_cfg(tmp_path)
        data_dir = cfg.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)

        # Write staff.parquet directly (no StaffSpy mock needed here)
        staff = [Staff.model_validate(r) for r in GOLDEN_STAFF]
        write_staff_parquet(staff, data_dir / "staff.parquet")

        logger = runlog.RunLogger(cfg.run_log_dir)
        n = score_people(cfg, logger)

        assert n > 0, "score_people returned 0 people"
        people = json.loads((data_dir / "people_to_meet.json").read_text(encoding="utf-8"))
        for p in people:
            assert p.get("why"), f"person {p['name']} has empty why[] (AC-021 violated)"
            assert p.get("warmth_score", 0) > 0, f"person {p['name']} has warmth_score == 0"

    def test_draft_never_sends(self, tmp_path: Path) -> None:
        """OutreachDraft.sent is always False — the draft-only invariant (AC-031)."""
        from lcp import runlog
        from lcp.contracts import Staff
        from lcp.fetch_staff import write_staff_parquet
        from lcp.mcp_server import impl_draft_outreach
        from lcp.score_people import score_people

        cfg = _make_cfg(tmp_path)
        data_dir = cfg.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)

        staff = [Staff.model_validate(r) for r in GOLDEN_STAFF]
        write_staff_parquet(staff, data_dir / "staff.parquet")

        logger = runlog.RunLogger(cfg.run_log_dir)
        score_people(cfg, logger)

        people = json.loads((data_dir / "people_to_meet.json").read_text(encoding="utf-8"))
        for p in people:
            draft = impl_draft_outreach(cfg, logger, p["profile_url"])
            assert draft.get("sent") is False, (
                f"sent=True for {p['name']} — violates the draft-only invariant"
            )

    def test_shortlist_entries_valid_against_contract(self, tmp_path: Path) -> None:
        """Every shortlist entry parses against the ShortlistEntry pydantic contract."""
        from lcp import runlog
        from lcp.contracts import ShortlistEntry
        from lcp.fetch_jobs import fetch_jobs
        from lcp.rank_jobs import rank_jobs

        cfg = _make_cfg(tmp_path)
        logger = runlog.RunLogger(cfg.run_log_dir)
        fetch_jobs(cfg, logger, _scrape_fn=lambda **_kw: _jobspy_df_from_golden())
        rank_jobs(cfg, logger, _today=REFERENCE_DATE)

        shortlist = json.loads((cfg.data_dir / "shortlist.json").read_text(encoding="utf-8"))
        assert shortlist, "shortlist is empty — cannot validate contract"
        for raw in shortlist:
            entry = ShortlistEntry.model_validate(raw)
            assert 0.0 <= entry.score <= 1.0
            assert entry.job_id

    def test_people_to_meet_valid_against_contract(self, tmp_path: Path) -> None:
        """Every people_to_meet.json entry parses against the PersonToMeet contract."""
        from lcp import runlog
        from lcp.contracts import PersonToMeet, Staff
        from lcp.fetch_staff import write_staff_parquet
        from lcp.score_people import score_people

        cfg = _make_cfg(tmp_path)
        data_dir = cfg.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)

        staff = [Staff.model_validate(r) for r in GOLDEN_STAFF]
        write_staff_parquet(staff, data_dir / "staff.parquet")

        logger = runlog.RunLogger(cfg.run_log_dir)
        score_people(cfg, logger)

        people = json.loads((data_dir / "people_to_meet.json").read_text(encoding="utf-8"))
        assert people, "people_to_meet.json is empty — cannot validate contract"
        for raw in people:
            p = PersonToMeet.model_validate(raw)
            assert p.warmth_score >= 0.0
            assert p.profile_url


# ---------------------------------------------------------------------------
# lcp doctor components (post-populated-run verification)
# ---------------------------------------------------------------------------


class TestDoctorAfterPopulatedRun:
    """lcp doctor reads state counts + funnel; verify it works on populated + empty state."""

    def test_state_counts_non_empty_after_fetch_jobs(self, tmp_path: Path) -> None:
        """State.seen_jobs > 0 after fetch_jobs completes successfully."""
        from lcp import runlog
        from lcp.fetch_jobs import fetch_jobs
        from lcp.state import State

        cfg = _make_cfg(tmp_path)
        logger = runlog.RunLogger(cfg.run_log_dir)
        n = fetch_jobs(cfg, logger, _scrape_fn=lambda **_kw: _jobspy_df_from_golden())
        assert n > 0

        counts = State(cfg.sqlite_path).counts()
        assert counts["seen_jobs"] > 0, (
            f"State.seen_jobs == 0 after fetch_jobs wrote {n} jobs: {counts}"
        )

    def test_funnel_returns_zeros_on_empty_run_log(self, tmp_path: Path) -> None:
        """runlog.funnel() on an empty directory returns zero counts without crashing."""
        from lcp import runlog

        result = runlog.funnel(tmp_path / "nonexistent_runs")
        assert isinstance(result, dict), "funnel must return a dict"
        assert all(v == 0 for v in result.values()), (
            f"empty funnel should be all-zero; got {result}"
        )

    def test_doctor_reads_state_and_funnel_after_full_run(self, tmp_path: Path) -> None:
        """Doctor-equivalent: State.counts() and runlog.funnel() work after a full pipeline run."""
        from lcp import runlog
        from lcp.fetch_jobs import fetch_jobs
        from lcp.fetch_staff import fetch_staff
        from lcp.rank_jobs import rank_jobs
        from lcp.score_people import score_people
        from lcp.state import State

        cfg = _make_cfg(tmp_path)
        data_dir = cfg.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        logger = runlog.RunLogger(cfg.run_log_dir)

        # Run the full pipeline
        fetch_jobs(cfg, logger, _scrape_fn=lambda **_kw: _jobspy_df_from_golden())
        rank_jobs(cfg, logger, _today=REFERENCE_DATE)
        mock_ss = _staffspy_mock_module(GOLDEN_STAFF)
        with patch.dict(sys.modules, {"staffspy": mock_ss}):
            fetch_staff(cfg, ["TechCorp"], logger)
        score_people(cfg, logger)

        # State reads
        counts = State(cfg.sqlite_path).counts()
        assert isinstance(counts, dict), "counts() must return a dict"
        assert counts["seen_jobs"] > 0, "no seen_jobs after fetch_jobs"

        # Funnel reads
        f = runlog.funnel(cfg.run_log_dir)
        assert isinstance(f, dict), "funnel() must return a dict"
        assert f["jobs_fetched"] > 0, f"funnel.jobs_fetched == 0; funnel: {f}"
        assert f["shortlisted"] > 0, f"funnel.shortlisted == 0; funnel: {f}"
        assert f["people"] > 0, f"funnel.people == 0; funnel: {f}"
        assert f["people_to_meet"] > 0, f"funnel.people_to_meet == 0; funnel: {f}"
