"""Supplemental job source adapters + registry.  AC-011 extension.

Each adapter:
  - Returns [] if its source is disabled (jobs.sources.<name>.enabled = false).
  - HTTP via an injectable _client (default: requests) for test isolation.
  - Normalises to JobPost with job_id = f"<source>:<stable-id>".
  - SEC-1: never logs str(exc) — only error_type=type(exc).__name__.
  - Degrades gracefully: network/parse failure → log + return [].

SOURCE_REGISTRY maps source names to adapter callables.
Callers (fetch_jobs.py) iterate the registry; each adapter self-gates on its
enabled flag, so the loop is always safe to run unconditionally.

API investigation summary (2026-06-27)
---------------------------------------
arbetsformedlingen  LIVE  https://jobsearch.api.jobtechdev.se/search  (no key)
euraxess            BLOCKED  euraxess.ec.europa.eu — WAF / robots.txt 403 on all
                             programmatic access; no documented public REST API.
academictransfer    NO API   academictransfer.com is a Vue SPA; all probed API
                             paths (/api/jobs/, /jobs.rss/, XHR JSON) return 404.
"""

from __future__ import annotations

import hashlib
import math
from datetime import date, datetime
from typing import Any, Callable
from urllib.parse import quote as _url_quote

from .config import Config
from .contracts import JobPost
from .runlog import RunLogger


# ---------------------------------------------------------------------------
# Shared normalization helpers (kept local to avoid circular import with
# fetch_jobs.py which also defines similar helpers for JobSpy rows)
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


def _date_from_iso(val: str | None) -> date | None:
    """Parse an ISO-8601 datetime/date string to a date, or None."""
    if not val:
        return None
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Adzuna adapter (requires ADZUNA_APP_ID + ADZUNA_APP_KEY from .env)
# Config path: jobs.sources.adzuna.*
# ---------------------------------------------------------------------------

def _fetch_adzuna(
    cfg: Config,
    logger: RunLogger,
    *,
    _client: Any = None,
) -> list[JobPost]:
    """Fetch jobs from the Adzuna API (free NL/EU coverage; requires API key).

    Degrades gracefully: returns [] if disabled, env keys are absent, or the
    request fails.  SEC-1: the Adzuna URL embeds app_id/app_key as query params,
    so str(exc) is never logged — only error_type.

    Args:
        cfg:     Pipeline config.  Reads jobs.sources.adzuna.* keys.
        logger:  RunLogger for structured events.
        _client: Injectable HTTP client (default: requests).  Pass a mock in tests.

    Returns:
        List of JobPost objects, possibly empty.
    """
    import os

    if _client is None:
        import requests as _client  # type: ignore[no-redef]

    if not cfg.get("jobs.sources.adzuna.enabled", False):
        return []

    app_id = os.environ.get("ADZUNA_APP_ID", "")
    app_key = os.environ.get("ADZUNA_APP_KEY", "")
    if not (app_id and app_key):
        logger.event("adzuna_skip", reason="ADZUNA_APP_ID/ADZUNA_APP_KEY not set")
        return []

    country = cfg.get("jobs.sources.adzuna.country", "nl")
    search_terms: list[str] = cfg.get("jobs.search_terms") or []
    results_per_page = min(cfg.get("jobs.results_wanted", 50), 50)
    posts: list[JobPost] = []

    for term in search_terms:
        # NOTE: URL embeds app_id + app_key in query params — never log str(exc).
        url = (
            f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
            f"?app_id={app_id}&app_key={app_key}&results_per_page={results_per_page}"
            f"&what={_url_quote(term)}&content-type=application/json"
        )
        try:
            resp = _client.get(url, timeout=15)
            resp.raise_for_status()
            for item in resp.json().get("results", []):
                adzuna_id = str(item.get("id", ""))
                job_url = item.get("redirect_url") or ""
                if not job_url:
                    continue
                raw_id = adzuna_id or hashlib.md5(job_url.encode()).hexdigest()[:12]
                dp = _date_from_iso(item.get("created"))
                company_obj = item.get("company", {}) or {}
                location_obj = item.get("location", {}) or {}
                location_str = ", ".join(
                    filter(None, location_obj.get("area", []) + [location_obj.get("display_name")])
                )
                posts.append(JobPost(
                    job_id=f"adzuna:{raw_id}",
                    title=item.get("title") or "Unknown",
                    company=company_obj.get("display_name") or "",
                    job_url=job_url,
                    location=location_str or None,
                    salary_min=_float_or_none(item.get("salary_min")),
                    salary_max=_float_or_none(item.get("salary_max")),
                    salary_currency="EUR",
                    date_posted=dp,
                    description=_str_or_none(item.get("description")),
                    source="adzuna",
                ))
        except Exception as exc:  # noqa: BLE001
            # SEC-1: never log str(exc) — the URL embeds app_id / app_key
            logger.event(
                "fetch_error",
                source="adzuna",
                term=term,
                error_type=type(exc).__name__,
            )

    return posts


# ---------------------------------------------------------------------------
# Arbetsförmedlingen / JobTech (Sweden; free, no API key required)
# Config path: jobs.sources.arbetsformedlingen.*
# Endpoint: GET https://jobsearch.api.jobtechdev.se/search?q=<term>&limit=<n>
#           Header: accept: application/json
# ---------------------------------------------------------------------------

def _fetch_arbetsformedlingen(
    cfg: Config,
    logger: RunLogger,
    *,
    _client: Any = None,
) -> list[JobPost]:
    """Fetch jobs from the Swedish Public Employment Service (JobTech Dev API).

    The JobTech API is freely accessible without authentication and covers all
    Swedish job listings (Arbetsförmedlingen / Platsbanken).  Response shape::

        {
          "total": {"value": <int>},
          "hits": [
            {
              "id": "<str>",
              "headline": "<str>",
              "employer": {"name": "<str>"},
              "workplace_address": {
                "municipality": "<str>",
                "region": "<str>"
              },
              "webpage_url": "<str>",
              "publication_date": "<ISO-8601>",
              "description": {"text": "<str>"}
            },
            ...
          ]
        }

    Args:
        cfg:     Pipeline config.  Reads jobs.sources.arbetsformedlingen.* keys.
                 Falls back to jobs.search_terms when per-source keywords absent.
        logger:  RunLogger for structured events.
        _client: Injectable HTTP client (default: requests).  Pass a mock in tests.

    Returns:
        List of JobPost objects, possibly empty.
    """
    if _client is None:
        import requests as _client  # type: ignore[no-redef]

    if not cfg.get("jobs.sources.arbetsformedlingen.enabled", False):
        return []

    keywords: list[str] = (
        cfg.get("jobs.sources.arbetsformedlingen.keywords")
        or cfg.get("jobs.search_terms")
        or []
    )
    limit: int = cfg.get("jobs.sources.arbetsformedlingen.limit", 100)
    posts: list[JobPost] = []

    for term in keywords:
        try:
            resp = _client.get(
                "https://jobsearch.api.jobtechdev.se/search",
                params={"q": term, "limit": limit},
                headers={"accept": "application/json"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            for hit in data.get("hits", []):
                job_id_raw = _str_or_none(hit.get("id")) or ""
                job_url = _str_or_none(hit.get("webpage_url")) or ""
                if not job_url:
                    # Construct the canonical Platsbanken URL from the numeric ID.
                    job_url = (
                        f"https://arbetsformedlingen.se/platsbanken/annonser/{job_id_raw}"
                        if job_id_raw
                        else ""
                    )
                if not job_id_raw:
                    job_id_raw = hashlib.md5(job_url.encode("utf-8")).hexdigest()[:12]

                if not job_url:
                    continue  # skip hits with neither id nor webpage_url

                wp = hit.get("workplace_address") or {}
                location_parts = [
                    p for p in [wp.get("municipality"), wp.get("region")] if p
                ]
                location_str: str | None = ", ".join(location_parts) or None

                employer = hit.get("employer") or {}
                description_obj = hit.get("description") or {}

                posts.append(JobPost(
                    job_id=f"arbetsformedlingen:{job_id_raw}",
                    title=hit.get("headline") or "Unknown",
                    company=_str_or_none(employer.get("name")) or "",
                    job_url=job_url,
                    location=location_str,
                    date_posted=_date_from_iso(hit.get("publication_date")),
                    description=_str_or_none(description_obj.get("text")),
                    source="arbetsformedlingen",
                ))
        except Exception as exc:  # noqa: BLE001
            # SEC-1: error_type only — arbetsformedlingen has no secret keys, but
            # we maintain the same defensive pattern as all other adapters.
            logger.event(
                "fetch_error",
                source="arbetsformedlingen",
                term=term,
                error_type=type(exc).__name__,
            )

    return posts


# ---------------------------------------------------------------------------
# EURAXESS (EU research jobs) — shell adapter; no public API available
# Config path: jobs.sources.euraxess.*
#
# Investigation (2026-06-27):
#   All programmatic access to euraxess.ec.europa.eu is blocked by the WAF /
#   CloudFront rules (HTTP 403 "Disallowed by robots.txt" on every tried path:
#   /api/jobs, /api/jobs/search, /europass/rest/jobs/search, /jobs/search).
#   No documented public REST or RSS endpoint exists.
#   Adapter is wired + config-toggleable so it can be enabled once an official
#   API becomes available without changes to fetch_jobs.py.
# ---------------------------------------------------------------------------

def _fetch_euraxess(
    cfg: Config,
    logger: RunLogger,
    *,
    _client: Any = None,
) -> list[JobPost]:
    """EURAXESS adapter — no stable public API; logs and returns [] when enabled.

    Args:
        cfg:     Pipeline config.  Reads jobs.sources.euraxess.enabled.
        logger:  RunLogger for structured events.
        _client: Injectable HTTP client (accepted for interface parity; unused
                 until a real endpoint is available).

    Returns:
        Always [] — either because disabled, or because no public API exists.
    """
    if not cfg.get("jobs.sources.euraxess.enabled", False):
        return []

    logger.event(
        "source_skip",
        source="euraxess",
        reason="no_public_api",
        detail=(
            "euraxess.ec.europa.eu blocks programmatic access (WAF/robots.txt 403); "
            "no stable public JSON endpoint confirmed as of 2026-06-27"
        ),
    )
    return []


# ---------------------------------------------------------------------------
# AcademicTransfer (NL academic jobs) — shell adapter; no public API available
# Config path: jobs.sources.academictransfer.*
#
# Investigation (2026-06-27):
#   academictransfer.com is a Vue.js SPA.  All probed paths return 404:
#   /api/jobs/?format=json, /en/jobs.rss/, /nl/jobs.rss/,
#   https://api.academictransfer.com/v1/jobs.
#   The site's job search XHR is not exposed as a documented public endpoint.
#   Adapter is wired + config-toggleable for future enablement.
# ---------------------------------------------------------------------------

def _fetch_academictransfer(
    cfg: Config,
    logger: RunLogger,
    *,
    _client: Any = None,
) -> list[JobPost]:
    """AcademicTransfer adapter — no stable public API; logs and returns [] when enabled.

    Args:
        cfg:     Pipeline config.  Reads jobs.sources.academictransfer.enabled.
        logger:  RunLogger for structured events.
        _client: Injectable HTTP client (accepted for interface parity; unused
                 until a real endpoint is available).

    Returns:
        Always [] — either because disabled, or because no public API exists.
    """
    if not cfg.get("jobs.sources.academictransfer.enabled", False):
        return []

    logger.event(
        "source_skip",
        source="academictransfer",
        reason="no_public_api",
        detail=(
            "academictransfer.com is a Vue SPA; no public JSON/RSS API confirmed "
            "as of 2026-06-27 (all probed endpoints returned 404)"
        ),
    )
    return []


# ---------------------------------------------------------------------------
# Registry — single import point for fetch_jobs.py
# ---------------------------------------------------------------------------

#: Maps source name → adapter callable with signature
#: ``(cfg: Config, logger: RunLogger) -> list[JobPost]``.
#: Each adapter self-gates on its own ``jobs.sources.<name>.enabled`` flag.
SOURCE_REGISTRY: dict[str, Callable] = {
    "adzuna": _fetch_adzuna,
    "arbetsformedlingen": _fetch_arbetsformedlingen,
    "euraxess": _fetch_euraxess,
    "academictransfer": _fetch_academictransfer,
}
