"""Tests for `lcp jobs export` CLI command. AC-export.

Covers:
  - shortlist export writes shortlist.csv with required columns
  - jobs export writes jobs.csv from parquet
  - --out path override works
  - printed output contains the written path
  - export is deterministic (no network calls)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from lcp.cli import app

RUNNER = CliRunner()

REQUIRED_SHORTLIST_COLS = {
    "score",
    "relevant",
    "relevance_terms",
    "company",
    "title",
    "location",
    "date_posted",
    "source",
    "job_url",
    "reasons",
}


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path) -> Path:
    """Write a minimal valid config.yaml to tmp_path and return the path."""
    raw = {
        "meta": {"data_dir": str(tmp_path)},
        "ranking": {"shortlist_size": 25, "min_score": 0.40},
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
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(raw), encoding="utf-8")
    return cfg_path


def _write_jobs_parquet(tmp_path: Path) -> None:
    """Write a small jobs.parquet to tmp_path."""
    rows = [
        {
            "job_id": "linkedin:J001",
            "title": "Bioinformatician",
            "company": "LifeSci BV",
            "location": "Amsterdam, Netherlands",
            "date_posted": pd.Timestamp("2026-06-25"),
            "source": "linkedin",
            "job_url": "https://li.com/jobs/J001",
            "description": "Work with human genomics data.",
            "remote": False,
            "salary_min": None,
            "salary_max": None,
            "salary_currency": "EUR",
            "job_level": "mid",
            "company_industry": "Biotech",
            "company_url": None,
            "first_seen": pd.Timestamp("2026-06-26"),
        },
        {
            "job_id": "indeed:J002",
            "title": "Data Engineer",
            "company": "TechCo",
            "location": "Rotterdam, Netherlands",
            "date_posted": pd.Timestamp("2026-06-24"),
            "source": "indeed",
            "job_url": "https://indeed.com/jobs/J002",
            "description": "Data pipeline work.",
            "remote": None,
            "salary_min": 70000.0,
            "salary_max": 90000.0,
            "salary_currency": "EUR",
            "job_level": "senior",
            "company_industry": "Technology",
            "company_url": None,
            "first_seen": pd.Timestamp("2026-06-26"),
        },
    ]
    df = pd.DataFrame(rows)
    tmp_path.mkdir(parents=True, exist_ok=True)
    df.to_parquet(tmp_path / "jobs.parquet", index=False)


def _write_shortlist_json(tmp_path: Path) -> None:
    """Write a small shortlist.json to tmp_path."""
    shortlist = [
        {
            "job_id": "linkedin:J001",
            "score": 0.85,
            "reasons": ["role match: bioinformatician", "location: Amsterdam"],
            "title": "Bioinformatician",
            "company": "LifeSci BV",
            "relevant": True,
            "relevance_terms": ["genomics", "bioinformatic"],
        },
        {
            "job_id": "indeed:J002",
            "score": 0.72,
            "reasons": ["salary: 70,000 EUR >= 60,000 EUR floor"],
            "title": "Data Engineer",
            "company": "TechCo",
            "relevant": None,
            "relevance_terms": [],
        },
    ]
    (tmp_path / "shortlist.json").write_text(json.dumps(shortlist, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Shortlist export tests
# ---------------------------------------------------------------------------


class TestExportShortlist:
    def test_shortlist_csv_written(self, tmp_path: Path) -> None:
        """lcp jobs export --what shortlist creates shortlist.csv."""
        cfg_path = _write_config(tmp_path)
        _write_jobs_parquet(tmp_path)
        _write_shortlist_json(tmp_path)

        result = RUNNER.invoke(app, [
            "jobs", "export",
            "--what", "shortlist",
            "--config", str(cfg_path),
        ])
        assert result.exit_code == 0, f"exit={result.exit_code}; output={result.output}"
        assert (tmp_path / "shortlist.csv").exists()

    def test_shortlist_csv_has_required_columns(self, tmp_path: Path) -> None:
        """shortlist.csv must contain all REQUIRED_SHORTLIST_COLS."""
        cfg_path = _write_config(tmp_path)
        _write_jobs_parquet(tmp_path)
        _write_shortlist_json(tmp_path)

        RUNNER.invoke(app, [
            "jobs", "export", "--what", "shortlist",
            "--config", str(cfg_path),
        ])

        with open(tmp_path / "shortlist.csv", newline="") as f:
            cols = set(csv.DictReader(f).fieldnames or [])

        missing = REQUIRED_SHORTLIST_COLS - cols
        assert not missing, f"shortlist.csv missing columns: {missing}. Got: {sorted(cols)}"

    def test_shortlist_csv_row_count(self, tmp_path: Path) -> None:
        """shortlist.csv has one row per shortlist entry."""
        cfg_path = _write_config(tmp_path)
        _write_jobs_parquet(tmp_path)
        _write_shortlist_json(tmp_path)

        RUNNER.invoke(app, [
            "jobs", "export", "--what", "shortlist",
            "--config", str(cfg_path),
        ])

        with open(tmp_path / "shortlist.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2

    def test_shortlist_csv_score_values(self, tmp_path: Path) -> None:
        """score column contains the float values from shortlist.json."""
        cfg_path = _write_config(tmp_path)
        _write_jobs_parquet(tmp_path)
        _write_shortlist_json(tmp_path)

        RUNNER.invoke(app, [
            "jobs", "export", "--what", "shortlist",
            "--config", str(cfg_path),
        ])

        with open(tmp_path / "shortlist.csv", newline="") as f:
            rows = list(csv.DictReader(f))

        scores = {float(r["score"]) for r in rows}
        assert 0.85 in scores
        assert 0.72 in scores

    def test_shortlist_csv_location_joined_from_parquet(self, tmp_path: Path) -> None:
        """location column comes from jobs.parquet (not in shortlist.json)."""
        cfg_path = _write_config(tmp_path)
        _write_jobs_parquet(tmp_path)
        _write_shortlist_json(tmp_path)

        RUNNER.invoke(app, [
            "jobs", "export", "--what", "shortlist",
            "--config", str(cfg_path),
        ])

        with open(tmp_path / "shortlist.csv", newline="") as f:
            rows = list(csv.DictReader(f))

        locations = {r["location"] for r in rows}
        assert "Amsterdam, Netherlands" in locations

    def test_export_out_override(self, tmp_path: Path) -> None:
        """--out writes to the specified path instead of the default."""
        cfg_path = _write_config(tmp_path)
        _write_jobs_parquet(tmp_path)
        _write_shortlist_json(tmp_path)
        custom = tmp_path / "custom_shortlist.csv"

        result = RUNNER.invoke(app, [
            "jobs", "export", "--what", "shortlist",
            "--config", str(cfg_path),
            "--out", str(custom),
        ])
        assert result.exit_code == 0, result.output
        assert custom.exists()
        assert not (tmp_path / "shortlist.csv").exists(), "default path must not be written"

    def test_export_prints_written_path(self, tmp_path: Path) -> None:
        """CLI output contains the written file path."""
        cfg_path = _write_config(tmp_path)
        _write_jobs_parquet(tmp_path)
        _write_shortlist_json(tmp_path)

        result = RUNNER.invoke(app, [
            "jobs", "export", "--what", "shortlist",
            "--config", str(cfg_path),
        ])
        assert result.exit_code == 0
        # path or filename must appear in output
        assert "shortlist.csv" in result.output or str(tmp_path) in result.output

    def test_shortlist_export_no_parquet_still_works(self, tmp_path: Path) -> None:
        """If jobs.parquet is absent, export fills join columns with empty strings."""
        cfg_path = _write_config(tmp_path)
        # Intentionally NOT writing jobs.parquet
        _write_shortlist_json(tmp_path)

        result = RUNNER.invoke(app, [
            "jobs", "export", "--what", "shortlist",
            "--config", str(cfg_path),
        ])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "shortlist.csv").exists()

        with open(tmp_path / "shortlist.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2   # both entries still exported


# ---------------------------------------------------------------------------
# Jobs export tests
# ---------------------------------------------------------------------------


class TestExportJobs:
    def test_jobs_csv_written(self, tmp_path: Path) -> None:
        """lcp jobs export --what jobs creates jobs.csv."""
        cfg_path = _write_config(tmp_path)
        _write_jobs_parquet(tmp_path)

        result = RUNNER.invoke(app, [
            "jobs", "export", "--what", "jobs",
            "--config", str(cfg_path),
        ])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "jobs.csv").exists()

    def test_jobs_csv_row_count_matches_parquet(self, tmp_path: Path) -> None:
        """jobs.csv has the same number of rows as jobs.parquet."""
        cfg_path = _write_config(tmp_path)
        _write_jobs_parquet(tmp_path)

        RUNNER.invoke(app, [
            "jobs", "export", "--what", "jobs",
            "--config", str(cfg_path),
        ])

        original = pd.read_parquet(tmp_path / "jobs.parquet")
        exported = pd.read_csv(tmp_path / "jobs.csv")
        assert len(exported) == len(original)

    def test_jobs_out_override(self, tmp_path: Path) -> None:
        """--out override writes to the specified path."""
        cfg_path = _write_config(tmp_path)
        _write_jobs_parquet(tmp_path)
        custom = tmp_path / "my_jobs.csv"

        result = RUNNER.invoke(app, [
            "jobs", "export", "--what", "jobs",
            "--config", str(cfg_path),
            "--out", str(custom),
        ])
        assert result.exit_code == 0, result.output
        assert custom.exists()

    def test_jobs_export_no_parquet_exits_nonzero(self, tmp_path: Path) -> None:
        """If jobs.parquet is absent, jobs export exits with a non-zero code."""
        cfg_path = _write_config(tmp_path)
        # No parquet written

        result = RUNNER.invoke(app, [
            "jobs", "export", "--what", "jobs",
            "--config", str(cfg_path),
        ])
        assert result.exit_code != 0
