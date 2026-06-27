"""Fetch jobs from configured boards via JobSpy + supplemental source registry. AC-011.

Design decisions:
  - JobSpy is imported LAZILY inside fetch_jobs() so the lcp package installs and
    the CLI starts without the `jobs` extra installed.
  - `_scrape_fn` is an injectable keyword-only parameter for testing (default = real
    jobspy.scrape_jobs). Tests pass a lambda that returns a small mock DataFrame.
  - Per-board isolation: we call the scraper once per (board, term) pair inside a
    try/except so a single board failure never aborts the run.
  - Supplemental sources (Adzuna, Arbetsförmedlingen, EURAXESS, AcademicTransfer) are
    registered in SOURCE_REGISTRY (see lcp.sources).  Each adapter self-gates on its
    enabled flag; the registry loop always runs but is a no-op for disabled sources.
  - Accumulating parquet: jobs.parquet is a cumulative store across runs.  New rows
    are appended; the State DB tracks what's "seen" for dedup.
  - job_id = f"{source}:{board_id}" when the board returns an id field; falls back to
    f"{source}:{md5(job_url)[:12]}" to ensure a stable natural key.
  - date_posted is stored as pd.Timestamp (nullable) for consistent parquet types.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timezone
from typing import Callable

import pandas as pd

from .config import Config
from .contracts import JobPost
from .runlog import RunLogger
from .sources import SOURCE_REGISTRY, _fetch_adzuna  # noqa: F401 — _fetch_adzuna re-exported for tests
from .state import State


# ---------------------------------------------------------------------------
# Row normalisation helpers
# ---------------------------------------------------------------------------

def _str_or_none(val: object) -> str | None:
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    s = str(val).strip()
    return s if s else None


def _float_or_none(val: object) -> float | None:
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _bool_or_none(val: object) -> bool | None:
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    return bool(val)


def _date_or_none(val: object) -> date | None:
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    if isinstance(val, pd.Timestamp):
        return None if pd.isna(val) else val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, datetime):
        return val.date()
    try:
        ts = pd.Timestamp(val)
        return None if pd.isna(ts) else ts.date()
    except Exception:  # noqa: BLE001
        return None


def _normalize_row(row: pd.Series, source: str) -> JobPost | None:
    """Convert one JobSpy DataFrame row into a JobPost.

    Returns None if the row is missing the mandatory fields (job_url, title).
    """
    job_url = _str_or_none(row.get("job_url"))
    if not job_url:
        return None

    raw_id = _str_or_none(row.get("id"))
    if raw_id:
        job_id = f"{source}:{raw_id}"
    else:
        digest = hashlib.md5(job_url.encode("utf-8")).hexdigest()[:12]
        job_id = f"{source}:{digest}"

    title = _str_or_none(row.get("title")) or "Unknown"
    company = _str_or_none(row.get("company")) or _str_or_none(row.get("company_name")) or ""

    return JobPost(
        job_id=job_id,
        title=title,
        company=company,
        company_url=_str_or_none(row.get("company_url")),
        location=_str_or_none(row.get("location")),
        remote=_bool_or_none(row.get("is_remote")),
        salary_min=_float_or_none(row.get("min_amount")),
        salary_max=_float_or_none(row.get("max_amount")),
        salary_currency=_str_or_none(row.get("currency")),
        date_posted=_date_or_none(row.get("date_posted")),
        job_url=job_url,
        description=_str_or_none(row.get("description")),
        job_level=_str_or_none(row.get("job_level")),
        company_industry=_str_or_none(row.get("company_industry")),
        source=source,
    )


def _post_to_row(post: JobPost) -> dict:
    """Serialise JobPost to a flat dict suitable for a pandas DataFrame row."""
    d = post.model_dump()
    # Convert date/datetime to pd.Timestamp for consistent parquet storage.
    if d.get("date_posted"):
        d["date_posted"] = pd.Timestamp(d["date_posted"])
    if d.get("first_seen"):
        d["first_seen"] = pd.Timestamp(d["first_seen"])
    return d


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_jobs(
    cfg: Config,
    logger: RunLogger,
    *,
    _scrape_fn: Callable | None = None,
) -> int:
    """Scrape job boards, dedup vs state, write jobs.parquet + jobs.csv.

    Args:
        cfg:        Pipeline config (site_names, search_terms, proxies, etc.)
        logger:     RunLogger to record events.
        _scrape_fn: Optional override for ``jobspy.scrape_jobs`` (DI for tests).
                    Called with keyword args: site_name, search_term, location,
                    country_indeed, results_wanted, hours_old, proxies.

    Returns:
        Number of NEW jobs written this run (deduped against the state DB).
    """
    # Lazy import so the CLI starts without the jobs extra.
    if _scrape_fn is None:
        from jobspy import scrape_jobs as _real_scrape  # type: ignore[import]
        _scrape_fn = _real_scrape

    state = State(cfg.sqlite_path)
    freshness_days: int = cfg.get("state.job_freshness_days", 30)

    site_names: list[str] = cfg.get("jobs.site_names") or ["linkedin"]
    search_terms: list[str] = cfg.get("jobs.search_terms") or []
    location: str = cfg.get("jobs.location") or "Amsterdam, Netherlands"
    country_indeed: str = cfg.get("jobs.country_indeed") or "Netherlands"
    results_wanted: int = cfg.get("jobs.results_wanted") or 25
    hours_old: int = cfg.get("jobs.hours_old") or 168

    # Load proxy list (only when backend is not none)
    proxies_arg: list[str] | None = None
    if cfg.get("proxies.backend", "none") != "none":
        proxy_file = cfg.data_dir / "good_proxies.json"
        if proxy_file.exists():
            loaded = json.loads(proxy_file.read_text())
            proxies_arg = loaded if loaded else None

    # Load existing accumulated jobs.parquet
    parquet_path = cfg.data_dir / "jobs.parquet"
    if parquet_path.exists():
        try:
            existing_df = pd.read_parquet(parquet_path)
        except Exception:  # noqa: BLE001
            existing_df = pd.DataFrame()
    else:
        existing_df = pd.DataFrame()

    # Scrape per (board, term) for isolation: a failing board never aborts the run.
    new_posts: list[JobPost] = []

    for term in search_terms:
        for board in site_names:
            try:
                result_df: pd.DataFrame = _scrape_fn(
                    site_name=board,
                    search_term=term,
                    location=location,
                    country_indeed=country_indeed,
                    results_wanted=results_wanted,
                    hours_old=hours_old,
                    proxies=proxies_arg,
                )
            except Exception as exc:  # noqa: BLE001
                # never log str(exc): a webshare proxy URL (user:pass@host) can appear in it (SEC-2)
                logger.event("fetch_error", board=board, term=term, error_type=type(exc).__name__)
                continue

            if result_df is None or result_df.empty:
                continue

            for _, row in result_df.iterrows():
                # Use the board name from the row's "site" column when available,
                # otherwise fall back to the board we requested.
                source = _str_or_none(row.get("site")) or board
                post = _normalize_row(row, source)
                if post is None:
                    continue
                is_new = state.record_job(
                    post.job_id,
                    title=post.title,
                    company=post.company,
                    job_url=post.job_url,
                    source=post.source,
                )
                if is_new:
                    new_posts.append(post)

    # Supplemental sources — iterate the registry; each adapter self-gates on its
    # enabled flag (returns [] when disabled), so this loop is unconditional.
    # Outer try/except isolates a broken adapter from aborting the entire run.
    for _source_name, _source_fn in SOURCE_REGISTRY.items():
        try:
            _source_posts = _source_fn(cfg, logger)
        except Exception as exc:  # noqa: BLE001
            logger.event(
                "fetch_error",
                source=_source_name,
                error_type=type(exc).__name__,
            )
            continue
        for post in _source_posts:
            is_new = state.record_job(
                post.job_id,
                title=post.title,
                company=post.company,
                job_url=post.job_url,
                source=post.source,
            )
            if is_new:
                new_posts.append(post)

    # Merge new posts into the accumulated parquet.
    if new_posts:
        new_rows = [_post_to_row(p) for p in new_posts]
        new_df = pd.DataFrame(new_rows)
        all_df = pd.concat([existing_df, new_df], ignore_index=True) if not existing_df.empty else new_df
    else:
        all_df = existing_df

    if not all_df.empty:
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        all_df.to_parquet(parquet_path, index=False)
        all_df.to_csv(cfg.data_dir / "jobs.csv", index=False)

    logger.event(
        "fetch_jobs",
        count_in=len(all_df),
        count_out=len(new_posts),
        boards=site_names,
        terms=search_terms,
    )
    return len(new_posts)
