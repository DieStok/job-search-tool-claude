"""Tests for lcp.sources — supplemental job source adapters + registry.

Covers:
  - arbetsformedlingen: normalization, job_id scheme, disabled→[], HTTP error→[],
    no secret in run-log (SEC-1 defensive pattern even without keys)
  - euraxess: disabled→[], enabled→source_skip logged + [], graceful when client raises
  - academictransfer: disabled→[], enabled→source_skip logged + [], graceful when raises
  - fetch_jobs integration: enabled source called, results deduplicated
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lcp.config import Config
from lcp.runlog import RunLogger


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _cfg(tmp_path: Path, overrides: dict | None = None) -> Config:
    """Minimal Config for source adapter tests."""
    raw: dict = {
        "meta": {"data_dir": str(tmp_path)},
        "jobs": {
            "site_names": ["linkedin"],
            "search_terms": ["data engineer"],
            "results_wanted": 10,
            "hours_old": 168,
            "location": "Amsterdam, Netherlands",
            "country_indeed": "Netherlands",
            "sources": {
                "adzuna": {"enabled": False},
                "arbetsformedlingen": {"enabled": False},
                "euraxess": {"enabled": False},
                "academictransfer": {"enabled": False},
            },
        },
        "proxies": {
            "backend": "none",
            "check_target": "linkedin",
            "in_process": {"static_list": []},
        },
        "state": {
            "sqlite_path": str(tmp_path / "state.sqlite"),
            "job_freshness_days": 30,
        },
        "compliance": {"require_human_send": True, "max_daily_outreach": 20},
        "observability": {"run_log_dir": str(tmp_path / "runs")},
        "orchestration": {"mcp_mode": "custom_pipeline", "scheduler": "launchd"},
        "outreach": {"mode": "draft_only"},
        "people": {
            "provider": "linkedin_mcp",
            "staffspy": {"account_mode": "main", "captcha_solver": "none"},
        },
        "enrichment": {"mode": "mcp"},
    }
    if overrides:
        # Deep-merge top-level keys only (sufficient for tests)
        for k, v in overrides.items():
            if isinstance(v, dict) and isinstance(raw.get(k), dict):
                raw[k].update(v)
            else:
                raw[k] = v
    return Config(raw=raw, profile={}, rubric={}, source_path=tmp_path / "config.yaml")


def _logger(tmp_path: Path) -> RunLogger:
    return RunLogger(tmp_path / "runs")


def _log_events(logger: RunLogger) -> list[dict]:
    return [json.loads(ln) for ln in logger.path.read_text().splitlines()]


# ---------------------------------------------------------------------------
# Realistic JobTech API fixture (matches live API structure confirmed 2026-06-27)
# ---------------------------------------------------------------------------

JOBTECH_FIXTURE: dict = {
    "total": {"value": 106},
    "hits": [
        {
            "id": "31206914",
            "headline": "Data Engineer",
            "employer": {
                "name": "RIKSBANKEN",
                "workplace_id": "abc123",
            },
            "workplace_address": {
                "municipality": "Stockholm",
                "region": "Stockholms län",
                "country": "Sverige",
                "street_address": "Brunkebergstorg 11",
            },
            "webpage_url": "https://arbetsformedlingen.se/platsbanken/annonser/31206914",
            "publication_date": "2026-06-23T14:13:36",
            "description": {
                "text": "We are looking for an experienced Data Engineer.",
                "text_formatted": "<p>We are looking for an experienced Data Engineer.</p>",
            },
        },
        {
            "id": "31207000",
            "headline": "Machine Learning Engineer",
            "employer": {"name": "AI Startup AB"},
            "workplace_address": {
                "municipality": "Göteborg",
                "region": "Västra Götalands län",
                "country": "Sverige",
            },
            "webpage_url": "https://arbetsformedlingen.se/platsbanken/annonser/31207000",
            "publication_date": "2026-06-22T09:00:00",
            "description": {"text": "Join our ML team."},
        },
    ],
}


def _mock_client(json_data: dict, status_code: int = 200) -> MagicMock:
    """Build a mock requests-like client returning json_data."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    else:
        resp.raise_for_status.return_value = None

    client = MagicMock()
    client.get.return_value = resp
    return client


def _raising_client(exc: Exception) -> MagicMock:
    """Build a mock requests-like client whose .get() raises exc."""
    client = MagicMock()
    client.get.side_effect = exc
    return client


# ---------------------------------------------------------------------------
# arbetsformedlingen tests
# ---------------------------------------------------------------------------

class TestArbetsformedlingen:
    def _enabled_cfg(self, tmp_path: Path, **source_kwargs) -> Config:
        base = {"enabled": True, **source_kwargs}
        return _cfg(tmp_path, {"jobs": {"sources": {"arbetsformedlingen": base}}})

    def test_disabled_returns_empty(self, tmp_path):
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = _cfg(tmp_path)  # arbetsformedlingen.enabled defaults to False
        result = _fetch_arbetsformedlingen(cfg, _logger(tmp_path), _client=_mock_client(JOBTECH_FIXTURE))
        assert result == []

    def test_enabled_returns_posts(self, tmp_path):
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path)
        result = _fetch_arbetsformedlingen(
            cfg, _logger(tmp_path), _client=_mock_client(JOBTECH_FIXTURE)
        )
        assert len(result) == 2

    def test_job_id_scheme(self, tmp_path):
        """job_id must be f'arbetsformedlingen:<id>' (not a url-hash)."""
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path)
        result = _fetch_arbetsformedlingen(
            cfg, _logger(tmp_path), _client=_mock_client(JOBTECH_FIXTURE)
        )
        assert result[0].job_id == "arbetsformedlingen:31206914"
        assert result[1].job_id == "arbetsformedlingen:31207000"

    def test_normalization_title_and_company(self, tmp_path):
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path)
        result = _fetch_arbetsformedlingen(
            cfg, _logger(tmp_path), _client=_mock_client(JOBTECH_FIXTURE)
        )
        post = result[0]
        assert post.title == "Data Engineer"
        assert post.company == "RIKSBANKEN"

    def test_normalization_location(self, tmp_path):
        """Location is municipality + region joined by ', '."""
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path)
        result = _fetch_arbetsformedlingen(
            cfg, _logger(tmp_path), _client=_mock_client(JOBTECH_FIXTURE)
        )
        assert result[0].location == "Stockholm, Stockholms län"

    def test_normalization_job_url(self, tmp_path):
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path)
        result = _fetch_arbetsformedlingen(
            cfg, _logger(tmp_path), _client=_mock_client(JOBTECH_FIXTURE)
        )
        assert result[0].job_url == "https://arbetsformedlingen.se/platsbanken/annonser/31206914"

    def test_normalization_date_posted(self, tmp_path):
        import datetime
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path)
        result = _fetch_arbetsformedlingen(
            cfg, _logger(tmp_path), _client=_mock_client(JOBTECH_FIXTURE)
        )
        assert result[0].date_posted == datetime.date(2026, 6, 23)

    def test_normalization_description(self, tmp_path):
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path)
        result = _fetch_arbetsformedlingen(
            cfg, _logger(tmp_path), _client=_mock_client(JOBTECH_FIXTURE)
        )
        assert "Data Engineer" in result[0].description

    def test_normalization_source_field(self, tmp_path):
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path)
        result = _fetch_arbetsformedlingen(
            cfg, _logger(tmp_path), _client=_mock_client(JOBTECH_FIXTURE)
        )
        for post in result:
            assert post.source == "arbetsformedlingen"

    def test_http_error_returns_empty(self, tmp_path):
        """Network/HTTP failures degrade gracefully: [] not an exception."""
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path)
        client = _raising_client(ConnectionError("connection refused"))
        result = _fetch_arbetsformedlingen(cfg, _logger(tmp_path), _client=client)
        assert result == []

    def test_http_error_logged_as_fetch_error(self, tmp_path):
        """Fetch errors are logged with error_type only (SEC-1 pattern)."""
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path)
        logger = _logger(tmp_path)
        _fetch_arbetsformedlingen(
            cfg, logger, _client=_raising_client(ConnectionError("refused"))
        )
        events = _log_events(logger)
        err_events = [e for e in events if e.get("stage") == "fetch_error"]
        assert err_events, "expected a fetch_error event"
        evt = err_events[0]
        assert evt.get("source") == "arbetsformedlingen"
        assert "error_type" in evt
        assert "error_msg" not in evt  # never log raw exception message (SEC-1)

    def test_no_secret_in_runlog_on_error(self, tmp_path):
        """AF has no API key, but we verify the log contains no embedded URL
        or exception detail that could carry credentials in a future version."""
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path)
        logger = _logger(tmp_path)
        _fetch_arbetsformedlingen(
            cfg,
            logger,
            _client=_raising_client(
                RuntimeError("error for url https://jobsearch.api.jobtechdev.se/search?secret=TOKEN")
            ),
        )
        log_text = logger.path.read_text()
        assert "TOKEN" not in log_text, "raw exception message leaked into run-log"

    def test_per_source_keywords_override(self, tmp_path):
        """jobs.sources.arbetsformedlingen.keywords takes priority over jobs.search_terms."""
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path, keywords=["bioinformatics"])
        client = _mock_client({"hits": []})
        _fetch_arbetsformedlingen(cfg, _logger(tmp_path), _client=client)

        call_kwargs = client.get.call_args
        assert call_kwargs.kwargs["params"]["q"] == "bioinformatics"

    def test_fallback_to_search_terms(self, tmp_path):
        """When no per-source keywords, falls back to jobs.search_terms."""
        from lcp.sources import _fetch_arbetsformedlingen

        cfg = self._enabled_cfg(tmp_path)  # no keywords override
        client = _mock_client({"hits": []})
        _fetch_arbetsformedlingen(cfg, _logger(tmp_path), _client=client)

        call_kwargs = client.get.call_args
        assert call_kwargs.kwargs["params"]["q"] == "data engineer"

    def test_fallback_job_url_constructed_from_id(self, tmp_path):
        """Hits missing webpage_url get a canonical Platsbanken URL from id."""
        from lcp.sources import _fetch_arbetsformedlingen

        fixture = {
            "hits": [
                {
                    "id": "99999",
                    "headline": "Test Job",
                    "employer": {"name": "Co"},
                    "workplace_address": {},
                    "publication_date": None,
                    "description": {},
                    # no webpage_url
                }
            ]
        }
        cfg = self._enabled_cfg(tmp_path)
        result = _fetch_arbetsformedlingen(cfg, _logger(tmp_path), _client=_mock_client(fixture))
        assert len(result) == 1
        assert "arbetsformedlingen.se/platsbanken/annonser/99999" in result[0].job_url

    def test_hit_without_id_or_url_skipped(self, tmp_path):
        """Hits with neither id nor webpage_url are silently dropped."""
        from lcp.sources import _fetch_arbetsformedlingen

        fixture = {"hits": [{"headline": "Ghost Job", "employer": {"name": "Nobody"}}]}
        cfg = self._enabled_cfg(tmp_path)
        result = _fetch_arbetsformedlingen(cfg, _logger(tmp_path), _client=_mock_client(fixture))
        assert result == []


# ---------------------------------------------------------------------------
# EURAXESS tests
# ---------------------------------------------------------------------------

class TestEuraxess:
    def test_disabled_returns_empty(self, tmp_path):
        from lcp.sources import _fetch_euraxess

        cfg = _cfg(tmp_path)  # euraxess.enabled defaults to False
        result = _fetch_euraxess(cfg, _logger(tmp_path), _client=_raising_client(ConnectionError()))
        assert result == []

    def test_enabled_returns_empty_and_logs_source_skip(self, tmp_path):
        """Enabled but no public API → source_skip event + []."""
        from lcp.sources import _fetch_euraxess

        cfg = _cfg(tmp_path, {"jobs": {"sources": {"euraxess": {"enabled": True}}}})
        logger = _logger(tmp_path)
        result = _fetch_euraxess(cfg, logger)
        assert result == []

        events = _log_events(logger)
        skip_events = [e for e in events if e.get("stage") == "source_skip"]
        assert skip_events, "expected a source_skip event when euraxess is enabled"
        assert skip_events[0]["source"] == "euraxess"
        assert skip_events[0]["reason"] == "no_public_api"

    def test_graceful_when_client_raises(self, tmp_path):
        """Even if a future implementation calls the client and it raises, result is []."""
        from lcp.sources import _fetch_euraxess

        cfg = _cfg(tmp_path, {"jobs": {"sources": {"euraxess": {"enabled": True}}}})
        # Pass a raising client — current shell ignores it, but the API contract holds
        result = _fetch_euraxess(
            cfg, _logger(tmp_path), _client=_raising_client(ConnectionError("network failure"))
        )
        assert result == []


# ---------------------------------------------------------------------------
# AcademicTransfer tests
# ---------------------------------------------------------------------------

class TestAcademicTransfer:
    def test_disabled_returns_empty(self, tmp_path):
        from lcp.sources import _fetch_academictransfer

        cfg = _cfg(tmp_path)  # academictransfer.enabled defaults to False
        result = _fetch_academictransfer(
            cfg, _logger(tmp_path), _client=_raising_client(ConnectionError())
        )
        assert result == []

    def test_enabled_returns_empty_and_logs_source_skip(self, tmp_path):
        """Enabled but no public API → source_skip event + []."""
        from lcp.sources import _fetch_academictransfer

        cfg = _cfg(tmp_path, {"jobs": {"sources": {"academictransfer": {"enabled": True}}}})
        logger = _logger(tmp_path)
        result = _fetch_academictransfer(cfg, logger)
        assert result == []

        events = _log_events(logger)
        skip_events = [e for e in events if e.get("stage") == "source_skip"]
        assert skip_events, "expected a source_skip event when academictransfer is enabled"
        assert skip_events[0]["source"] == "academictransfer"
        assert skip_events[0]["reason"] == "no_public_api"

    def test_graceful_when_client_raises(self, tmp_path):
        from lcp.sources import _fetch_academictransfer

        cfg = _cfg(tmp_path, {"jobs": {"sources": {"academictransfer": {"enabled": True}}}})
        result = _fetch_academictransfer(
            cfg, _logger(tmp_path), _client=_raising_client(ConnectionError("network failure"))
        )
        assert result == []


# ---------------------------------------------------------------------------
# SOURCE_REGISTRY shape test
# ---------------------------------------------------------------------------

class TestSourceRegistry:
    def test_registry_contains_expected_sources(self):
        from lcp.sources import SOURCE_REGISTRY

        assert "adzuna" in SOURCE_REGISTRY
        assert "arbetsformedlingen" in SOURCE_REGISTRY
        assert "euraxess" in SOURCE_REGISTRY
        assert "academictransfer" in SOURCE_REGISTRY

    def test_registry_values_are_callable(self):
        from lcp.sources import SOURCE_REGISTRY

        for name, fn in SOURCE_REGISTRY.items():
            assert callable(fn), f"SOURCE_REGISTRY[{name!r}] is not callable"


# ---------------------------------------------------------------------------
# fetch_jobs integration: enabled sources called + dedup
# ---------------------------------------------------------------------------

class TestFetchJobsIntegration:
    """Verify fetch_jobs.py iterates SOURCE_REGISTRY and dedups supplemental posts."""

    def _make_post(self, job_id: str, source: str = "arbetsformedlingen") -> "JobPost":
        from lcp.contracts import JobPost

        return JobPost(
            job_id=job_id,
            title="Test Job",
            company="TestCo",
            job_url=f"https://example.com/{job_id}",
            source=source,
        )

    def test_fetch_jobs_calls_enabled_source_and_returns_posts(self, tmp_path, monkeypatch):
        """Enabled source in SOURCE_REGISTRY is called; its posts appear in parquet."""
        import pandas as pd
        from lcp.fetch_jobs import fetch_jobs
        import lcp.fetch_jobs as fj

        expected_post = self._make_post("arbetsformedlingen:12345")
        mock_registry = {
            "arbetsformedlingen": lambda cfg, logger: [expected_post],
        }
        monkeypatch.setattr(fj, "SOURCE_REGISTRY", mock_registry)

        cfg = _cfg(tmp_path)
        n = fetch_jobs(cfg, _logger(tmp_path), _scrape_fn=lambda **_: pd.DataFrame())
        assert n == 1

        df = pd.read_parquet(tmp_path / "jobs.parquet")
        assert "arbetsformedlingen:12345" in df["job_id"].values

    def test_fetch_jobs_dedups_supplemental_posts(self, tmp_path, monkeypatch):
        """Same job_id from a supplemental source is NOT counted twice across runs."""
        import pandas as pd
        from lcp.fetch_jobs import fetch_jobs
        import lcp.fetch_jobs as fj

        post = self._make_post("arbetsformedlingen:dup001")
        mock_registry = {"arbetsformedlingen": lambda cfg, logger: [post]}
        monkeypatch.setattr(fj, "SOURCE_REGISTRY", mock_registry)

        cfg = _cfg(tmp_path)
        logger = _logger(tmp_path)

        n1 = fetch_jobs(cfg, logger, _scrape_fn=lambda **_: pd.DataFrame())
        n2 = fetch_jobs(cfg, logger, _scrape_fn=lambda **_: pd.DataFrame())

        assert n1 == 1
        assert n2 == 0  # deduped on second run

        df = pd.read_parquet(tmp_path / "jobs.parquet")
        assert len(df) == 1  # still only 1 row, not 2

    def test_fetch_jobs_source_failure_does_not_abort_run(self, tmp_path, monkeypatch):
        """If one registry source raises, other sources still contribute."""
        import pandas as pd
        from lcp.fetch_jobs import fetch_jobs
        import lcp.fetch_jobs as fj

        good_post = self._make_post("arbetsformedlingen:good001")

        def _bad_source(cfg, logger):
            raise RuntimeError("source exploded")

        mock_registry = {
            "bad_source": _bad_source,
            "arbetsformedlingen": lambda cfg, logger: [good_post],
        }
        monkeypatch.setattr(fj, "SOURCE_REGISTRY", mock_registry)

        cfg = _cfg(tmp_path)
        n = fetch_jobs(cfg, _logger(tmp_path), _scrape_fn=lambda **_: pd.DataFrame())
        # good_post still captured despite bad_source raising
        assert n == 1

    def test_fetch_jobs_multiple_sources_combined(self, tmp_path, monkeypatch):
        """Posts from multiple registry sources are all written to parquet."""
        import pandas as pd
        from lcp.fetch_jobs import fetch_jobs
        import lcp.fetch_jobs as fj

        post_a = self._make_post("arbetsformedlingen:a001")
        post_e = self._make_post("euraxess:e001", source="euraxess")

        mock_registry = {
            "arbetsformedlingen": lambda cfg, logger: [post_a],
            "euraxess": lambda cfg, logger: [post_e],
        }
        monkeypatch.setattr(fj, "SOURCE_REGISTRY", mock_registry)

        cfg = _cfg(tmp_path)
        n = fetch_jobs(cfg, _logger(tmp_path), _scrape_fn=lambda **_: pd.DataFrame())
        assert n == 2

        df = pd.read_parquet(tmp_path / "jobs.parquet")
        assert set(df["job_id"]) == {"arbetsformedlingen:a001", "euraxess:e001"}
