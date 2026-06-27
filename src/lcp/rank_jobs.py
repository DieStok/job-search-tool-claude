"""Deterministic job ranking: rubric pre-filter + weighted score → shortlist. AC-012.

Algorithm
---------
1. Pre-filter  — drop excluded_titles (case-insensitive substring) and avoid_companies.
2. Score each surviving job against five weighted signals from rubric.yaml:
     role_match      0..1  — any desired_title is a substring of the job title
     seniority_match 0..1  — job_level contains any desired seniority keyword
     location_match  0..1  — location contains "amsterdam" OR (remote_ok AND is_remote)
     salary_match    0..1  — salary_min >= salary_floor (0 if unknown; 1 if no floor set)
     recency         0..1  — linear decay: 1 − (age_days / recency_days), clamped [0,1]
3. Weighted sum → score in [0,1] (weights already sum to 1 in the example rubric).
4. Drop below ranking.min_score; keep top ranking.shortlist_size.
5. Sort: score DESC, job_id ASC (stable, fully deterministic for identical input).
6. Emit data/shortlist.json as list of ShortlistEntry dicts.

Inject ``_today`` (a datetime.date) for deterministic tests; defaults to date.today().
"""

from __future__ import annotations

import json
import math
from datetime import date, timedelta

import pandas as pd

from .config import Config
from .contracts import ShortlistEntry
from .runlog import RunLogger


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _role_match(title: str, desired_titles: list[str]) -> tuple[float, str | None]:
    if not desired_titles or not title:
        return 0.0, None
    t = title.lower()
    for dt in desired_titles:
        if dt.lower() in t:
            return 1.0, f"role match: {dt}"
    return 0.0, None


def _seniority_match(job_level: str | None, desired: list[str]) -> tuple[float, str | None]:
    if not job_level or not desired:
        return 0.0, None
    lvl = job_level.lower()
    for d in desired:
        if d.lower() in lvl:
            return 1.0, f"seniority match: {d}"
    return 0.0, None


def _location_match(
    location: str | None,
    is_remote: bool | None,
    mode: str,
    remote_ok: bool,
) -> tuple[float, str | None]:
    loc = (location or "").lower()
    if mode == "anywhere_eu":
        return 1.0, "location: anywhere EU"
    if "amsterdam" in loc:
        return 1.0, f"location: Amsterdam ({location})"
    if mode == "netherlands":
        # credit any NL location (city or country) — for nationwide searches (e.g. PhD positions)
        nl_cities = ("netherlands", "nederland", "utrecht", "rotterdam", "the hague", "den haag",
                     "leiden", "delft", "eindhoven", "groningen", "nijmegen", "wageningen",
                     "maastricht", "enschede", "tilburg", "twente", "amersfoort", "bilthoven",
                     "hilversum", "haarlem", "zwolle", "arnhem")
        if any(c in loc for c in nl_cities):
            return 1.0, f"location: Netherlands ({location})"
        if remote_ok and is_remote:
            return 1.0, "location: remote OK"
        return 0.0, None
    if remote_ok and is_remote:
        return 1.0, "location: remote OK"
    if mode == "amsterdam_or_remote" and remote_ok and is_remote:
        return 1.0, "location: remote OK"
    return 0.0, None


def _salary_match(
    salary_min: float | None,
    floor: float,
) -> tuple[float, str | None]:
    if floor <= 0:
        return 1.0, None  # no floor configured → neutral pass
    if salary_min is None or (isinstance(salary_min, float) and math.isnan(salary_min)):
        return 0.0, None  # unknown → cannot verify
    if salary_min >= floor:
        return 1.0, f"salary: {salary_min:,.0f} EUR >= {floor:,.0f} EUR floor"
    return 0.0, None


def _recency_score(
    date_posted: object,
    today: date,
    recency_days: int,
) -> tuple[float, str | None]:
    # pd.isna robustly catches None, float nan, AND pd.NaT (missing date_posted is common in
    # live job data — JobSpy often returns NaT). Guard before any date arithmetic.
    try:
        if date_posted is None or pd.isna(date_posted):
            return 0.0, None
    except (TypeError, ValueError):
        return 0.0, None
    # Normalise to a date object
    if isinstance(date_posted, pd.Timestamp):
        posted = date_posted.date()
    elif isinstance(date_posted, date):
        posted = date_posted
    else:
        try:
            ts = pd.Timestamp(date_posted)
            if pd.isna(ts):
                return 0.0, None
            posted = ts.date()
        except Exception:  # noqa: BLE001
            return 0.0, None

    age = (today - posted).days
    if age < 0:
        age = 0  # future-dated jobs score as brand-new
    score = max(0.0, 1.0 - age / recency_days)
    if score > 0:
        return score, f"recency: posted {age} day{'s' if age != 1 else ''} ago"
    return 0.0, None


# ---------------------------------------------------------------------------
# Pre-filter helper
# ---------------------------------------------------------------------------

def _is_excluded_title(title: str, excluded_titles: list[str]) -> bool:
    t = title.lower()
    return any(ex.lower() in t for ex in excluded_titles)


def _is_avoided_company(company: str, avoid_companies: list[str]) -> bool:
    c = company.lower()
    return any(av.lower() in c for av in avoid_companies)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rank_jobs(
    cfg: Config,
    logger: RunLogger,
    *,
    _today: date | None = None,
) -> int:
    """Read jobs.parquet, score + filter, write shortlist.json.

    Args:
        cfg:    Pipeline config (ranking params from cfg.raw; weights from cfg.rubric).
        logger: RunLogger to record the ``rank_jobs`` event.
        _today: Reference date for recency scoring (default = date.today(); inject in tests).

    Returns:
        Number of jobs in the shortlist.
    """
    today = _today or date.today()

    # -- Read input parquet ---------------------------------------------------
    parquet_path = cfg.data_dir / "jobs.parquet"
    if not parquet_path.exists():
        logger.event("rank_jobs", count_in=0, count_out=0,
                     note="jobs.parquet not found; nothing to rank")
        _write_shortlist(cfg, [])
        return 0

    df = pd.read_parquet(parquet_path)
    if df.empty:
        logger.event("rank_jobs", count_in=0, count_out=0,
                     note="jobs.parquet is empty")
        _write_shortlist(cfg, [])
        return 0

    # Normalise date_posted to consistent Timestamps
    if "date_posted" in df.columns:
        df["date_posted"] = pd.to_datetime(df["date_posted"], errors="coerce")

    # -- Pull rubric config ---------------------------------------------------
    jobs_rubric: dict = cfg.rubric.get("jobs", {})
    desired_titles: list[str] = jobs_rubric.get("desired_titles", [])
    excluded_titles: list[str] = jobs_rubric.get("excluded_titles", [])
    desired_seniority: list[str] = (jobs_rubric.get("seniority", {}) or {}).get("desired", [])
    location_cfg: dict = jobs_rubric.get("location", {}) or {}
    location_mode: str = location_cfg.get("mode", "amsterdam_or_remote")
    remote_ok: bool = bool(location_cfg.get("remote_ok", True))
    salary_floor: float = float(jobs_rubric.get("salary_floor_eur", 0) or 0)
    recency_days: int = int(jobs_rubric.get("recency_days", 14) or 14)
    avoid_companies: list[str] = (jobs_rubric.get("company_preferences", {}) or {}).get(
        "avoid_companies", []
    )

    weights_cfg: dict = jobs_rubric.get("weights", {}) or {}
    w_role = float(weights_cfg.get("role_match", 0.35))
    w_seniority = float(weights_cfg.get("seniority_match", 0.15))
    w_location = float(weights_cfg.get("location_match", 0.20))
    w_salary = float(weights_cfg.get("salary_match", 0.10))
    w_recency = float(weights_cfg.get("recency", 0.20))

    ranking_cfg: dict = cfg.get("ranking") or {}
    min_score: float = float(ranking_cfg.get("min_score", 0.4) or 0.4)
    shortlist_size: int = int(ranking_cfg.get("shortlist_size", 25) or 25)

    # -- Relevance filter config -----------------------------------------------
    # jobs.relevance controls an optional keyword pre-filter applied AFTER the
    # rubric score.  This is a cheap substring pass; Claude judgment refines it.
    # Config keys (see config/config.example.yaml for allowed values):
    #   enabled    bool   – false = no-op; true = compute relevant + relevance_terms
    #   include_any list  – job is 'relevant' if ANY term appears in scanned fields
    #   exclude_any list  – job is excluded (relevant=False) if ANY term appears (overrides include)
    #   scan       list   – fields to search; OPTIONS: title | description
    #   mode       str    – 'tag' = annotate only; 'filter' = drop non-relevant entries
    # See lcp/rank_jobs.py and lcp/contracts.ShortlistEntry for the output contract.
    _rel_cfg: dict = (cfg.get("jobs.relevance") or {}) or {}
    rel_enabled: bool = bool(_rel_cfg.get("enabled", False))
    rel_include: list[str] = list(_rel_cfg.get("include_any") or [])
    rel_exclude: list[str] = list(_rel_cfg.get("exclude_any") or [])
    rel_scan: list[str] = list(_rel_cfg.get("scan") or ["title", "description"])
    rel_mode: str = str(_rel_cfg.get("mode") or "tag")  # OPTIONS: tag | filter

    # -- Pre-filter -----------------------------------------------------------
    count_in = len(df)
    mask_title = df["title"].apply(
        lambda t: not _is_excluded_title(str(t) if t is not None else "", excluded_titles)
    )
    mask_company = df["company"].apply(
        lambda c: not _is_avoided_company(str(c) if c is not None else "", avoid_companies)
    )
    df = df[mask_title & mask_company].copy()

    if df.empty:
        logger.event("rank_jobs", count_in=count_in, count_out=0,
                     note="all jobs filtered out by pre-filter")
        _write_shortlist(cfg, [])
        return 0

    # -- Score ----------------------------------------------------------------
    entries: list[ShortlistEntry] = []

    for _, row in df.iterrows():
        reasons: list[str] = []

        r_role, hint_role = _role_match(str(row.get("title") or ""), desired_titles)
        r_seniority, hint_sen = _seniority_match(
            _str_or_none(row.get("job_level")), desired_seniority
        )
        r_location, hint_loc = _location_match(
            _str_or_none(row.get("location")),
            _bool_or_none(row.get("remote")),
            location_mode,
            remote_ok,
        )
        r_salary, hint_sal = _salary_match(
            _float_or_none(row.get("salary_min")), salary_floor
        )
        r_recency, hint_rec = _recency_score(row.get("date_posted"), today, recency_days)

        score = (
            r_role * w_role
            + r_seniority * w_seniority
            + r_location * w_location
            + r_salary * w_salary
            + r_recency * w_recency
        )

        for hint in (hint_role, hint_sen, hint_loc, hint_sal, hint_rec):
            if hint:
                reasons.append(hint)

        # -- Relevance annotation ------------------------------------------------
        # Compute per-job relevant flag and matched terms when filter is enabled.
        # relevant=None and relevance_terms=[] when filter is disabled.
        _relevant: bool | None = None
        _relevance_terms: list[str] = []
        if rel_enabled:
            # Build the text to scan from the configured fields.
            _scan_text = " ".join(
                str(row.get(field) or "") for field in rel_scan
            ).lower()
            _matched_include = [t for t in rel_include if t.lower() in _scan_text]
            _matched_exclude = [t for t in rel_exclude if t.lower() in _scan_text]
            if _matched_exclude:
                # Exclude overrides include: job is not relevant regardless of includes.
                _relevant = False
                # Still record which include terms matched for traceability.
                _relevance_terms = _matched_include
            elif _matched_include:
                _relevant = True
                _relevance_terms = _matched_include
            else:
                _relevant = False
                _relevance_terms = []

        entries.append(ShortlistEntry(
            job_id=str(row.get("job_id") or ""),
            score=round(score, 6),
            reasons=reasons,
            title=_str_or_none(row.get("title")),
            company=_str_or_none(row.get("company")),
            relevant=_relevant,
            relevance_terms=_relevance_terms,
        ))

    # -- Filter + sort --------------------------------------------------------
    entries = [e for e in entries if e.score >= min_score]
    # Deterministic: score DESC, then job_id ASC as tie-breaker
    entries.sort(key=lambda e: (-e.score, e.job_id))
    entries = entries[:shortlist_size]

    # Relevance post-filter: when mode=filter, drop non-relevant entries.
    # This runs AFTER score filtering + sort so the cap applies to the full scored set.
    if rel_enabled and rel_mode == "filter":
        entries = [e for e in entries if e.relevant]

    # -- Write output ---------------------------------------------------------
    _write_shortlist(cfg, entries)

    logger.event("rank_jobs", count_in=count_in, count_out=len(entries))
    return len(entries)


def _write_shortlist(cfg: Config, entries: list[ShortlistEntry]) -> None:
    out_path = cfg.data_dir / "shortlist.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [e.model_dump() for e in entries]
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# Private helpers (module-level for consistency with proxy_check pattern)
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
