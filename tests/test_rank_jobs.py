"""AC-012 — rank_jobs: golden input -> deterministic order, non-empty reasons, score in [0,1].

All tests use a fixed reference_date (2026-06-27) injected via `_today` so scores
are stable regardless of when the suite runs.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from lcp.config import Config
from lcp.runlog import RunLogger

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "eval" / "golden" / "jobs_sample.json"
REFERENCE_DATE = date(2026, 6, 27)

# Expected order by job_id (score desc, then job_id asc for ties).
# Derived from rubric.example.yaml weights + golden data dates.
EXPECTED_ORDER = ["linkedin:1001", "linkedin:1002", "glassdoor:3001", "indeed:2001"]
EXCLUDED_JOB = "indeed:2002"   # "Sales Manager" -> excluded_titles contains "sales"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(tmp_path: Path) -> Config:
    """Config pointing to tmp_path, using example rubric (no live config needed)."""
    repo = Path(__file__).resolve().parents[1]
    raw = {
        "meta": {"data_dir": str(tmp_path)},
        "ranking": {"shortlist_size": 25, "min_score": 0.40},
        "state": {"sqlite_path": str(tmp_path / "state.sqlite"), "job_freshness_days": 30},
        "compliance": {"require_human_send": True, "max_daily_outreach": 20},
        "observability": {"run_log_dir": str(tmp_path / "runs")},
        "orchestration": {
            "mcp_mode": "custom_pipeline",
            "scheduler": "launchd",
        },
        "outreach": {"mode": "draft_only"},
        "people": {
            "provider": "linkedin_mcp",
            "staffspy": {"account_mode": "main", "captcha_solver": "none"},
        },
        "enrichment": {"mode": "mcp"},
    }
    # Load rubric from example so we test against the canonical weights.
    import yaml
    rubric = yaml.safe_load((repo / "config" / "rubric.example.yaml").read_text())
    return Config(raw=raw, profile={}, rubric=rubric, source_path=tmp_path / "config.yaml")


def _logger(tmp_path: Path) -> RunLogger:
    return RunLogger(tmp_path / "runs")


def _write_golden_parquet(tmp_path: Path) -> None:
    """Load golden JSON and write to tmp_path/jobs.parquet (as fetch_jobs would)."""
    records = json.loads(GOLDEN_PATH.read_text())
    df = pd.DataFrame(records)
    # Match the types that fetch_jobs produces.
    df["date_posted"] = pd.to_datetime(df["date_posted"], errors="coerce")
    df["first_seen"] = pd.to_datetime(df["first_seen"], errors="coerce")
    # Ensure nullable booleans handled correctly
    df["remote"] = df["remote"].where(df["remote"].notna(), other=None)
    tmp_path.mkdir(parents=True, exist_ok=True)
    df.to_parquet(tmp_path / "jobs.parquet", index=False)


# ---------------------------------------------------------------------------
# Core determinism tests
# ---------------------------------------------------------------------------

class TestRankJobsDeterminism:
    def test_golden_expected_order(self, tmp_path):
        """Golden input -> fixed order: 1001 > 1002 > 3001 > 2001."""
        from lcp.rank_jobs import rank_jobs

        _write_golden_parquet(tmp_path)
        rank_jobs(_cfg(tmp_path), _logger(tmp_path), _today=REFERENCE_DATE)

        shortlist = json.loads((tmp_path / "shortlist.json").read_text())
        job_ids = [e["job_id"] for e in shortlist]
        assert job_ids == EXPECTED_ORDER, (
            f"expected {EXPECTED_ORDER}, got {job_ids}"
        )

    def test_same_input_same_output(self, tmp_path):
        """Running rank_jobs twice on identical input produces identical output."""
        from lcp.rank_jobs import rank_jobs

        _write_golden_parquet(tmp_path)
        cfg = _cfg(tmp_path)
        logger = _logger(tmp_path)

        rank_jobs(cfg, logger, _today=REFERENCE_DATE)
        first_run = json.loads((tmp_path / "shortlist.json").read_text())

        rank_jobs(cfg, logger, _today=REFERENCE_DATE)
        second_run = json.loads((tmp_path / "shortlist.json").read_text())

        assert first_run == second_run, "rank_jobs is non-deterministic"


# ---------------------------------------------------------------------------
# AC-012: scores and reasons
# ---------------------------------------------------------------------------

class TestShortlistEntryShape:
    def test_all_entries_have_score_in_range(self, tmp_path):
        from lcp.rank_jobs import rank_jobs

        _write_golden_parquet(tmp_path)
        rank_jobs(_cfg(tmp_path), _logger(tmp_path), _today=REFERENCE_DATE)

        shortlist = json.loads((tmp_path / "shortlist.json").read_text())
        assert shortlist, "shortlist is empty"
        for e in shortlist:
            assert 0.0 <= e["score"] <= 1.0, f"score out of range: {e}"

    def test_all_entries_have_non_empty_reasons(self, tmp_path):
        """Each shortlist entry cites >= 1 reason (which signals matched)."""
        from lcp.rank_jobs import rank_jobs

        _write_golden_parquet(tmp_path)
        rank_jobs(_cfg(tmp_path), _logger(tmp_path), _today=REFERENCE_DATE)

        shortlist = json.loads((tmp_path / "shortlist.json").read_text())
        for e in shortlist:
            assert e.get("reasons"), f"entry {e['job_id']} has empty reasons"

    def test_excluded_job_absent(self, tmp_path):
        """Jobs matching excluded_titles are dropped before scoring."""
        from lcp.rank_jobs import rank_jobs

        _write_golden_parquet(tmp_path)
        rank_jobs(_cfg(tmp_path), _logger(tmp_path), _today=REFERENCE_DATE)

        shortlist = json.loads((tmp_path / "shortlist.json").read_text())
        ids = {e["job_id"] for e in shortlist}
        assert EXCLUDED_JOB not in ids, f"{EXCLUDED_JOB} should be excluded (sales title)"

    def test_entries_match_shortlistentry_contract(self, tmp_path):
        from lcp.contracts import ShortlistEntry
        from lcp.rank_jobs import rank_jobs

        _write_golden_parquet(tmp_path)
        rank_jobs(_cfg(tmp_path), _logger(tmp_path), _today=REFERENCE_DATE)

        shortlist = json.loads((tmp_path / "shortlist.json").read_text())
        for e in shortlist:
            parsed = ShortlistEntry.model_validate(e)
            assert parsed.job_id
            assert 0.0 <= parsed.score <= 1.0


# ---------------------------------------------------------------------------
# AC-012: pre-filter and scoring edge cases
# ---------------------------------------------------------------------------

class TestPreFilter:
    def test_below_min_score_dropped(self, tmp_path):
        """Jobs scoring below min_score are not in the shortlist."""
        from lcp.rank_jobs import rank_jobs

        _write_golden_parquet(tmp_path)
        cfg = _cfg(tmp_path)
        # Raise min_score so the low-scoring job (indeed:2001 ~ 0.77) is kept but
        # a hypothetical 0.3-scorer would be dropped.  We confirm the threshold
        # logic by setting it above indeed:2001's score (0.77 > 0.40 baseline).
        cfg.raw["ranking"]["min_score"] = 0.95  # Only 1001 and 1002 should pass
        rank_jobs(cfg, _logger(tmp_path), _today=REFERENCE_DATE)

        shortlist = json.loads((tmp_path / "shortlist.json").read_text())
        ids = [e["job_id"] for e in shortlist]
        assert "linkedin:1001" in ids
        assert "linkedin:1002" in ids
        # 3001 scores 0.90 which is < 0.95, so it should be dropped
        assert "glassdoor:3001" not in ids

    def test_shortlist_size_cap(self, tmp_path):
        """shortlist_size caps how many entries are returned."""
        from lcp.rank_jobs import rank_jobs

        _write_golden_parquet(tmp_path)
        cfg = _cfg(tmp_path)
        cfg.raw["ranking"]["shortlist_size"] = 2
        rank_jobs(cfg, _logger(tmp_path), _today=REFERENCE_DATE)

        shortlist = json.loads((tmp_path / "shortlist.json").read_text())
        assert len(shortlist) <= 2
        # Top-2 should be the highest-scoring pair
        assert shortlist[0]["job_id"] == "linkedin:1001"
        assert shortlist[1]["job_id"] == "linkedin:1002"


# ---------------------------------------------------------------------------
# AC-012: missing parquet handled gracefully
# ---------------------------------------------------------------------------

class TestGracefulDegradation:
    def test_missing_parquet_returns_zero(self, tmp_path):
        from lcp.rank_jobs import rank_jobs

        cfg = _cfg(tmp_path)
        n = rank_jobs(cfg, _logger(tmp_path), _today=REFERENCE_DATE)
        assert n == 0

    def test_missing_parquet_writes_empty_shortlist(self, tmp_path):
        from lcp.rank_jobs import rank_jobs

        rank_jobs(_cfg(tmp_path), _logger(tmp_path), _today=REFERENCE_DATE)
        shortlist = json.loads((tmp_path / "shortlist.json").read_text())
        assert shortlist == []


# ---------------------------------------------------------------------------
# AC-012: run-log event
# ---------------------------------------------------------------------------

class TestRankJobsRunlog:
    def test_event_written_with_count_out(self, tmp_path):
        from lcp.rank_jobs import rank_jobs

        _write_golden_parquet(tmp_path)
        logger = _logger(tmp_path)
        n = rank_jobs(_cfg(tmp_path), logger, _today=REFERENCE_DATE)

        events = [json.loads(ln) for ln in logger.path.read_text().splitlines()]
        evt = next((e for e in events if e.get("stage") == "rank_jobs"), None)
        assert evt is not None, "rank_jobs event not written"
        assert evt["count_out"] == n


def test_recency_handles_missing_date_nat():
    """Live jobs often have NaT/None date_posted — recency must not crash (regression 2026-06-27)."""
    import pandas as pd
    from datetime import date
    from lcp.rank_jobs import _recency_score
    for missing in (None, pd.NaT, float("nan")):
        score, hint = _recency_score(missing, date(2026, 6, 27), 14)
        assert score == 0.0 and hint is None


def test_location_mode_netherlands():
    """netherlands mode credits NL cities + remote, rejects elsewhere (nationwide search)."""
    from lcp.rank_jobs import _location_match as _location_score
    assert _location_score("Utrecht, Netherlands", False, "netherlands", True)[0] == 1.0
    assert _location_score("Wageningen, GE, NL", False, "netherlands", True)[0] == 1.0
    assert _location_score("Berlin, Germany", False, "netherlands", True)[0] == 0.0
    assert _location_score("Remote", True, "netherlands", True)[0] == 1.0
