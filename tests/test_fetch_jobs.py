"""AC-011 — fetch_jobs: mocked JobSpy, parquet written, dedup, board isolation.

All JobSpy network calls are replaced by the `_scrape_fn` injection; no real HTTP.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from lcp.config import Config
from lcp.runlog import RunLogger
from lcp.state import State


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _cfg(
    tmp_path: Path,
    site_names: list[str] | None = None,
    search_terms: list[str] | None = None,
    backend: str = "none",
) -> Config:
    raw = {
        "meta": {"data_dir": str(tmp_path)},
        "jobs": {
            "site_names": site_names or ["linkedin"],
            "search_terms": search_terms or ["data engineer"],
            "results_wanted": 10,
            "hours_old": 168,
            "location": "Amsterdam, Netherlands",
            "country_indeed": "Netherlands",
            # All supplemental sources disabled by default (new config path AC-011)
            "sources": {
                "adzuna": {"enabled": False},
                "arbetsformedlingen": {"enabled": False},
                "euraxess": {"enabled": False},
                "academictransfer": {"enabled": False},
            },
        },
        "proxies": {
            "backend": backend,
            "check_target": "linkedin",
            "in_process": {"static_list": []},
        },
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
    return Config(raw=raw, profile={}, rubric={}, source_path=tmp_path / "config.yaml")


def _logger(tmp_path: Path) -> RunLogger:
    return RunLogger(tmp_path / "runs")


def _mock_df(*rows: dict) -> pd.DataFrame:
    """Build a minimal DataFrame that matches the JobSpy desired_order columns."""
    defaults = {
        "id": None,
        "site": "linkedin",
        "job_url": "https://linkedin.com/jobs/view/0",
        "job_url_direct": None,
        "title": "Data Engineer",
        "company": "TestCo",
        "location": "Amsterdam, Netherlands",
        "date_posted": pd.Timestamp("2026-06-26"),
        "job_type": None,
        "salary_source": None,
        "interval": None,
        "min_amount": None,
        "max_amount": None,
        "currency": "EUR",
        "is_remote": False,
        "job_level": "mid",
        "job_function": None,
        "listing_type": None,
        "emails": None,
        "description": "Test job description.",
        "company_industry": "Technology",
        "company_url": None,
        "company_logo": None,
        "company_url_direct": None,
        "company_addresses": None,
        "company_num_employees": None,
        "company_revenue": None,
        "company_description": None,
        "skills": None,
        "experience_range": None,
        "company_rating": None,
        "company_reviews_count": None,
        "vacancy_count": None,
        "work_from_home_type": None,
    }
    data = [{**defaults, **r} for r in rows]
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# Core: parquet + CSV written, JobPost-valid
# ---------------------------------------------------------------------------

class TestFetchJobsArtifacts:
    def test_parquet_and_csv_written(self, tmp_path):
        from lcp.fetch_jobs import fetch_jobs

        mock_df = _mock_df(
            {"id": "J001", "site": "linkedin", "job_url": "https://li/J001",
             "title": "Senior Data Engineer", "company": "DataCo",
             "location": "Amsterdam, Netherlands", "min_amount": 80000.0,
             "max_amount": 100000.0, "currency": "EUR", "is_remote": False,
             "job_level": "senior"},
        )
        cfg = _cfg(tmp_path)
        n = fetch_jobs(cfg, _logger(tmp_path), _scrape_fn=lambda **_: mock_df)

        assert n == 1
        assert (tmp_path / "jobs.parquet").exists()
        assert (tmp_path / "jobs.csv").exists()

    def test_returned_df_is_jobpost_valid(self, tmp_path):
        """Every row in jobs.parquet must parse as a valid JobPost."""
        from lcp.contracts import JobPost
        from lcp.fetch_jobs import fetch_jobs

        mock_df = _mock_df(
            {"id": "J001", "site": "linkedin", "job_url": "https://li/J001",
             "title": "Data Engineer", "company": "Acme"},
            {"id": "J002", "site": "linkedin", "job_url": "https://li/J002",
             "title": "ML Engineer", "company": "Acme2",
             "date_posted": pd.Timestamp("2026-06-20")},
        )
        fetch_jobs(_cfg(tmp_path), _logger(tmp_path), _scrape_fn=lambda **_: mock_df)

        df = pd.read_parquet(tmp_path / "jobs.parquet")
        for _, row in df.iterrows():
            jp = JobPost.model_validate(row.to_dict())
            assert jp.job_id
            assert jp.source

    def test_returns_count_of_new_jobs(self, tmp_path):
        from lcp.fetch_jobs import fetch_jobs

        mock_df = _mock_df(
            {"id": "A1", "job_url": "https://li/A1"},
            {"id": "A2", "job_url": "https://li/A2"},
        )
        n = fetch_jobs(_cfg(tmp_path), _logger(tmp_path), _scrape_fn=lambda **_: mock_df)
        assert n == 2

    def test_empty_board_response_handled(self, tmp_path):
        """Board returning empty DataFrame: no crash, n=0."""
        from lcp.fetch_jobs import fetch_jobs

        n = fetch_jobs(_cfg(tmp_path), _logger(tmp_path),
                       _scrape_fn=lambda **_: pd.DataFrame())
        assert n == 0
        # parquet not written for zero jobs (or empty parquet OK)
        # we only assert no exception and n==0


# ---------------------------------------------------------------------------
# AC-011: dedup — re-run does NOT double-count
# ---------------------------------------------------------------------------

class TestDedup:
    def test_rerun_does_not_add_duplicates(self, tmp_path):
        from lcp.fetch_jobs import fetch_jobs

        mock_df = _mock_df(
            {"id": "D1", "site": "linkedin", "job_url": "https://li/D1",
             "title": "Data Engineer", "company": "Co"},
            {"id": "D2", "site": "linkedin", "job_url": "https://li/D2",
             "title": "ML Engineer", "company": "Co"},
        )
        cfg = _cfg(tmp_path)
        logger = _logger(tmp_path)

        # First run: 2 new jobs
        n1 = fetch_jobs(cfg, logger, _scrape_fn=lambda **_: mock_df)
        assert n1 == 2

        # Second run: same jobs -> 0 new
        n2 = fetch_jobs(cfg, logger, _scrape_fn=lambda **_: mock_df)
        assert n2 == 0

        # Parquet still has 2 rows (not 4)
        df = pd.read_parquet(tmp_path / "jobs.parquet")
        assert len(df) == 2

    def test_new_job_on_second_run_is_counted(self, tmp_path):
        from lcp.fetch_jobs import fetch_jobs

        run1 = _mock_df({"id": "E1", "job_url": "https://li/E1", "title": "Data Engineer"})
        run2 = _mock_df(
            {"id": "E1", "job_url": "https://li/E1", "title": "Data Engineer"},  # duplicate
            {"id": "E2", "job_url": "https://li/E2", "title": "ML Engineer"},    # new
        )
        cfg = _cfg(tmp_path)
        logger = _logger(tmp_path)

        n1 = fetch_jobs(cfg, logger, _scrape_fn=lambda **_: run1)
        n2 = fetch_jobs(cfg, logger, _scrape_fn=lambda **_: run2)

        assert n1 == 1
        assert n2 == 1   # only E2 is new

        df = pd.read_parquet(tmp_path / "jobs.parquet")
        assert len(df) == 2


# ---------------------------------------------------------------------------
# AC-011: board failure isolation
# ---------------------------------------------------------------------------

class TestBoardIsolation:
    def test_failing_board_does_not_crash_run(self, tmp_path):
        """If one board raises, others still produce output."""
        from lcp.fetch_jobs import fetch_jobs

        good_df = _mock_df({"id": "G1", "site": "indeed", "job_url": "https://indeed/G1",
                             "title": "Data Engineer", "company": "GoodCo"})

        call_n = [0]

        def selective_scraper(**kwargs):
            call_n[0] += 1
            # First call (linkedin) raises; second call (indeed) succeeds
            site = kwargs.get("site_name", "")
            if site == "linkedin":
                raise RuntimeError("linkedin scrape failed")
            return good_df

        cfg = _cfg(tmp_path, site_names=["linkedin", "indeed"],
                   search_terms=["data engineer"])
        logger = _logger(tmp_path)
        # Should not raise
        n = fetch_jobs(cfg, logger, _scrape_fn=selective_scraper)

        # indeed job was captured despite linkedin failure
        assert n >= 1

    def test_board_errors_logged(self, tmp_path):
        """Board failures are logged as fetch_error events."""
        from lcp.fetch_jobs import fetch_jobs

        def always_raises(**_):
            raise ConnectionError("board down")

        cfg = _cfg(tmp_path, site_names=["linkedin"])
        logger = _logger(tmp_path)
        fetch_jobs(cfg, logger, _scrape_fn=always_raises)

        events = [json.loads(ln) for ln in logger.path.read_text().splitlines()]
        assert any(e.get("stage") == "fetch_error" for e in events)


# ---------------------------------------------------------------------------
# AC-011: job_id generation (stable id or url-hash fallback)
# ---------------------------------------------------------------------------

class TestJobIdGeneration:
    def test_id_from_board_field(self, tmp_path):
        from lcp.fetch_jobs import fetch_jobs

        mock_df = _mock_df({"id": "LI12345", "site": "linkedin",
                             "job_url": "https://li.com/jobs/view/LI12345"})
        fetch_jobs(_cfg(tmp_path), _logger(tmp_path), _scrape_fn=lambda **_: mock_df)

        df = pd.read_parquet(tmp_path / "jobs.parquet")
        job_id = df.iloc[0]["job_id"]
        assert job_id == "linkedin:LI12345"

    def test_id_from_url_hash_when_id_null(self, tmp_path):
        from lcp.fetch_jobs import fetch_jobs

        mock_df = _mock_df({"id": None, "site": "glassdoor",
                             "job_url": "https://glassdoor.com/job/xyz"})
        fetch_jobs(_cfg(tmp_path), _logger(tmp_path), _scrape_fn=lambda **_: mock_df)

        df = pd.read_parquet(tmp_path / "jobs.parquet")
        job_id = df.iloc[0]["job_id"]
        assert job_id.startswith("glassdoor:")
        assert len(job_id) > len("glassdoor:")


# ---------------------------------------------------------------------------
# AC-011: run-log event
# ---------------------------------------------------------------------------

class TestRunlog:
    def test_fetch_jobs_event_written(self, tmp_path):
        from lcp.fetch_jobs import fetch_jobs

        logger = _logger(tmp_path)
        mock_df = _mock_df({"id": "Z1", "job_url": "https://li/Z1", "title": "DE"})
        fetch_jobs(_cfg(tmp_path), logger, _scrape_fn=lambda **_: mock_df)

        events = [json.loads(ln) for ln in logger.path.read_text().splitlines()]
        evt = next((e for e in events if e.get("stage") == "fetch_jobs"), None)
        assert evt is not None, "fetch_jobs event not written"
        assert "count_out" in evt
        assert evt["count_out"] == 1


# ---------------------------------------------------------------------------
# Multi-country support (jobs.countries config)
# ---------------------------------------------------------------------------


class TestMultiCountry:
    def test_multi_country_calls_scrape_per_country(self, tmp_path):
        """When jobs.countries is set, _scrape_fn is called once per (country, board, term)."""
        from lcp.fetch_jobs import fetch_jobs

        calls: list[dict] = []

        def recording_scraper(**kwargs):
            calls.append({"country": kwargs.get("country_indeed"), "location": kwargs.get("location")})
            return pd.DataFrame()  # empty — we only care about call count

        cfg = _cfg(tmp_path, site_names=["linkedin"], search_terms=["data engineer"])
        cfg.raw["jobs"]["countries"] = [
            {"country_indeed": "Netherlands", "location": "Netherlands"},
            {"country_indeed": "Germany", "location": "Germany"},
        ]
        fetch_jobs(cfg, _logger(tmp_path), _scrape_fn=recording_scraper)

        # One call per (country × board × term) = 2 × 1 × 1 = 2
        assert len(calls) == 2
        countries_seen = {c["country"] for c in calls}
        assert countries_seen == {"Netherlands", "Germany"}

    def test_multi_country_accumulates_results(self, tmp_path):
        """Results from all countries land in a single jobs.parquet."""
        from lcp.fetch_jobs import fetch_jobs

        nl_df = _mock_df({"id": "NL1", "site": "linkedin", "job_url": "https://li/NL1",
                           "title": "Data Engineer NL", "company": "NLCo"})
        de_df = _mock_df({"id": "DE1", "site": "linkedin", "job_url": "https://li/DE1",
                           "title": "Data Engineer DE", "company": "DECo"})

        country_dfs = {"Netherlands": nl_df, "Germany": de_df}

        def country_scraper(**kwargs):
            return country_dfs.get(kwargs.get("country_indeed"), pd.DataFrame())

        cfg = _cfg(tmp_path, site_names=["linkedin"], search_terms=["data engineer"])
        cfg.raw["jobs"]["countries"] = [
            {"country_indeed": "Netherlands", "location": "Netherlands"},
            {"country_indeed": "Germany", "location": "Germany"},
        ]
        n = fetch_jobs(cfg, _logger(tmp_path), _scrape_fn=country_scraper)

        assert n == 2, f"expected 2 new jobs, got {n}"
        df = pd.read_parquet(tmp_path / "jobs.parquet")
        assert len(df) == 2

    def test_multi_country_dedup_across_countries(self, tmp_path):
        """A job that appears in two countries is deduped to a single row."""
        from lcp.fetch_jobs import fetch_jobs

        shared_df = _mock_df({"id": "SHARED1", "site": "linkedin",
                               "job_url": "https://li/SHARED1",
                               "title": "EU-wide Data Engineer", "company": "EUCo"})

        cfg = _cfg(tmp_path, site_names=["linkedin"], search_terms=["data engineer"])
        cfg.raw["jobs"]["countries"] = [
            {"country_indeed": "Netherlands", "location": "Netherlands"},
            {"country_indeed": "Germany", "location": "Germany"},
        ]
        n = fetch_jobs(cfg, _logger(tmp_path), _scrape_fn=lambda **_: shared_df)

        # Only 1 unique job despite 2 countries
        assert n == 1, f"expected dedup to 1, got {n}"
        df = pd.read_parquet(tmp_path / "jobs.parquet")
        assert len(df) == 1

    def test_multi_country_per_country_failure_isolated(self, tmp_path):
        """A board failure in one country does not abort the other countries."""
        from lcp.fetch_jobs import fetch_jobs

        good_df = _mock_df({"id": "GOOD1", "site": "linkedin", "job_url": "https://li/GOOD1",
                             "title": "Good Job", "company": "GoodCo"})

        def selective_scraper(**kwargs):
            if kwargs.get("country_indeed") == "Germany":
                raise RuntimeError("DE board exploded")
            return good_df

        cfg = _cfg(tmp_path, site_names=["linkedin"], search_terms=["data engineer"])
        cfg.raw["jobs"]["countries"] = [
            {"country_indeed": "Netherlands", "location": "Netherlands"},
            {"country_indeed": "Germany", "location": "Germany"},
        ]
        # Should NOT raise even though Germany fails
        n = fetch_jobs(cfg, _logger(tmp_path), _scrape_fn=selective_scraper)
        assert n == 1, f"NL job should still be captured: got {n}"

    def test_empty_countries_falls_back_to_single_country(self, tmp_path):
        """jobs.countries = [] → single-country mode using country_indeed + location."""
        from lcp.fetch_jobs import fetch_jobs

        calls: list[dict] = []

        def recording_scraper(**kwargs):
            calls.append({"country": kwargs.get("country_indeed"), "location": kwargs.get("location")})
            return pd.DataFrame()

        cfg = _cfg(tmp_path, site_names=["linkedin"], search_terms=["data engineer"])
        cfg.raw["jobs"]["countries"] = []  # explicitly empty
        fetch_jobs(cfg, _logger(tmp_path), _scrape_fn=recording_scraper)

        # Should call once with the single country from config
        assert len(calls) == 1
        assert calls[0]["country"] == "Netherlands"

    def test_absent_countries_key_falls_back_to_single_country(self, tmp_path):
        """When jobs.countries is absent entirely, single-country mode is used."""
        from lcp.fetch_jobs import fetch_jobs

        calls: list[dict] = []

        def recording_scraper(**kwargs):
            calls.append({"country": kwargs.get("country_indeed")})
            return pd.DataFrame()

        cfg = _cfg(tmp_path, site_names=["linkedin"], search_terms=["data engineer"])
        # No 'countries' key at all
        cfg.raw["jobs"].pop("countries", None)
        fetch_jobs(cfg, _logger(tmp_path), _scrape_fn=recording_scraper)

        assert len(calls) == 1
        assert calls[0]["country"] == "Netherlands"


def test_adzuna_error_does_not_log_api_key(tmp_path, monkeypatch):
    """SEC-1 regression: an Adzuna failure must NOT write app_id/app_key to the run-log.

    _fetch_adzuna is re-exported from lcp.sources via lcp.fetch_jobs for backward compat.
    Config path migrated: jobs.sources.adzuna.enabled (was jobs.adzuna.enabled).
    """
    import lcp.fetch_jobs as fj
    from lcp.config import load_config
    from lcp.runlog import RunLogger
    from lcp.paths import repo_root
    monkeypatch.setenv("ADZUNA_APP_ID", "SECRET_ID_123")
    monkeypatch.setenv("ADZUNA_APP_KEY", "SECRET_KEY_456")
    cfg = load_config(repo_root() / "config" / "config.example.yaml")
    # Migrate to new config path: jobs.sources.adzuna.enabled
    cfg.raw.setdefault("jobs", {}).setdefault("sources", {}).setdefault("adzuna", {})["enabled"] = True
    cfg.raw["jobs"]["sources"]["adzuna"]["country"] = "nl"
    cfg.raw["jobs"]["search_terms"] = ["x"]
    # force the HTTP call to raise an error whose message embeds the key-bearing URL.
    # requests is imported inside _fetch_adzuna, so patch the requests module directly.
    import requests
    def boom(*a, **k):
        raise RuntimeError("HTTPSConnectionPool: failed for url https://api.adzuna.com/...?app_id=SECRET_ID_123&app_key=SECRET_KEY_456")
    monkeypatch.setattr(requests, "get", boom)
    logger = RunLogger(tmp_path)
    fj._fetch_adzuna(cfg, logger)
    log_text = "\n".join(p.read_text() for p in tmp_path.glob("*.jsonl"))
    assert "SECRET_ID_123" not in log_text and "SECRET_KEY_456" not in log_text
