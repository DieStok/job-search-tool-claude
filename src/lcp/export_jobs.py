"""Deterministic CSV export from shortlist.json + jobs.parquet.  No network.

Two export targets (controlled by the ``what`` argument):

    shortlist  — writes <data_dir>/shortlist.csv (default).  Joins shortlist.json
                 with jobs.parquet to add location, date_posted, source, and job_url.
                 Columns: score, relevant, relevance_terms, company, title, location,
                          date_posted, source, job_url, reasons.

    jobs       — writes <data_dir>/jobs.csv from the full jobs.parquet.

Both targets accept an optional ``--out`` path override.

Design decisions:
  - Pure read + write; no network calls, no State DB access.
  - relevance_terms (list) → pipe-separated string in CSV for human readability.
  - reasons (list) → "; "-separated string.
  - Missing parquet rows for a shortlist entry are handled gracefully (empty strings).
  - FileNotFoundError propagates for ``--what jobs`` when parquet is absent
    (nothing useful to export).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .config import Config
from .runlog import RunLogger

# Ordered column list for the shortlist CSV (stable across runs).
SHORTLIST_COLUMNS: list[str] = [
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
]


def export_jobs(
    cfg: Config,
    what: str,
    out: str | None,
    logger: RunLogger,
) -> Path:
    """Export shortlist or jobs data to CSV.

    Args:
        cfg:    Pipeline config (used for ``cfg.data_dir``).
        what:   Export target — ``"shortlist"`` or ``"jobs"``.
                Allowed values: shortlist | jobs
        out:    Optional output-path override.  When None, defaults to
                ``<data_dir>/shortlist.csv`` or ``<data_dir>/jobs.csv``.
        logger: RunLogger used to record the export event.

    Returns:
        Path to the written CSV file.

    Raises:
        ValueError: when ``what`` is not a recognised export target.
        FileNotFoundError: when ``what="jobs"`` and jobs.parquet is absent.
    """
    if what == "shortlist":
        return _export_shortlist(cfg.data_dir, out, logger)
    if what == "jobs":
        return _export_jobs_parquet(cfg.data_dir, out, logger)
    raise ValueError(
        f"Unknown export target: {what!r}.  Allowed values: shortlist | jobs"
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _export_jobs_parquet(data_dir: Path, out: str | None, logger: RunLogger) -> Path:
    """Write jobs.parquet → jobs.csv (or ``out`` if provided)."""
    parquet_path = data_dir / "jobs.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"jobs.parquet not found at {parquet_path}. "
            "Run `lcp jobs fetch` first."
        )
    df = pd.read_parquet(parquet_path)
    out_path = Path(out) if out else data_dir / "jobs.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    logger.event("export_jobs", what="jobs", rows=len(df), path=str(out_path))
    return out_path


def _export_shortlist(data_dir: Path, out: str | None, logger: RunLogger) -> Path:
    """Join shortlist.json with jobs.parquet → shortlist.csv (or ``out`` if provided).

    If jobs.parquet is absent, the join columns (location, date_posted, source,
    job_url) are left as empty strings — the shortlist data is still exported.
    """
    shortlist_path = data_dir / "shortlist.json"
    if not shortlist_path.exists():
        raise FileNotFoundError(
            f"shortlist.json not found at {shortlist_path}. "
            "Run `lcp jobs rank` first."
        )

    shortlist: list[dict] = json.loads(shortlist_path.read_text(encoding="utf-8"))

    # Build a job_id → row dict from parquet for the join.
    jobs_by_id: dict[str, dict] = {}
    parquet_path = data_dir / "jobs.parquet"
    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
        if not df.empty and "job_id" in df.columns:
            jobs_by_id = {str(row["job_id"]): row.to_dict() for _, row in df.iterrows()}

    rows: list[dict] = []
    for entry in shortlist:
        job_id = str(entry.get("job_id", ""))
        job_row: dict = jobs_by_id.get(job_id, {})

        # relevance_terms: list → pipe-separated string for CSV readability.
        rel_terms: list[str] = entry.get("relevance_terms") or []
        rel_terms_str = "|".join(rel_terms)

        # reasons: list → "; "-separated string.
        reasons: list[str] = entry.get("reasons") or []
        reasons_str = "; ".join(reasons)

        # date_posted: normalise pd.Timestamp / string → ISO date string.
        raw_date = job_row.get("date_posted")
        if raw_date is None or (isinstance(raw_date, float) and pd.isna(raw_date)):
            date_posted_str = ""
        elif isinstance(raw_date, pd.Timestamp):
            date_posted_str = "" if pd.isna(raw_date) else raw_date.strftime("%Y-%m-%d")
        else:
            date_posted_str = str(raw_date)

        rows.append({
            "score": entry.get("score"),
            "relevant": entry.get("relevant"),
            "relevance_terms": rel_terms_str,
            "company": entry.get("company") or job_row.get("company") or "",
            "title": entry.get("title") or job_row.get("title") or "",
            "location": job_row.get("location") or "",
            "date_posted": date_posted_str,
            "source": job_row.get("source") or "",
            "job_url": job_row.get("job_url") or "",
            "reasons": reasons_str,
        })

    out_df = pd.DataFrame(rows, columns=SHORTLIST_COLUMNS)
    out_path = Path(out) if out else data_dir / "shortlist.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False)
    logger.event("export_jobs", what="shortlist", rows=len(out_df), path=str(out_path))
    return out_path
