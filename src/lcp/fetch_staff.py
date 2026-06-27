"""D3 / AC-020 — StaffSpy wrapper for batch staff enumeration.

Rules (load-bearing, never weaken):
  - StaffSpy runs on the operator's OWN IP.  NEVER accepts or constructs a proxy.
  - `people.staffspy.max_profiles_per_company_per_day` is a hard ceiling enforced
    before and after every StaffSpy call.  Exceeding it raises StaffFetchCeilingError.
  - StaffSpy is imported LAZILY inside `fetch_staff()` so the CLI loads when the
    extra isn't installed and tests can mock via sys.modules.
  - If `people.provider == linkedin_mcp`, this function is a NO-OP stub (the
    interactive MCP layer handles people lookups; this Python batch path is not used).
  - Writes data/staff.parquet (overwrite-safe via a temp file rename).

Parquet row schema (JSON-serialised nested fields):
  company, name, title, profile_url, location,
  education   (JSON list of Education dicts),
  experiences (JSON list of Experience dicts),
  skills      (JSON list of str),
  email, contactable, source
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config
from .contracts import Education, Experience, Staff
from .runlog import RunLogger
from .state import State

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class StaffFetchCeilingError(RuntimeError):
    """Raised when the daily-per-company profile ceiling would be exceeded."""


# ---------------------------------------------------------------------------
# Parquet I/O helpers (used by score_people + tests)
# ---------------------------------------------------------------------------


def staff_to_row(s: Staff) -> dict:
    """Serialise a Staff object to a flat dict suitable for a parquet row."""
    return {
        "company": s.company,
        "name": s.name,
        "title": s.title,
        "profile_url": s.profile_url,
        "location": s.location,
        "education": json.dumps([e.model_dump() for e in s.education], default=str),
        "experiences": json.dumps([e.model_dump() for e in s.experiences], default=str),
        "skills": json.dumps(s.skills, default=str),
        "email": s.email,
        "contactable": s.contactable,
        "source": s.source,
    }


def row_to_staff(row: dict | Any) -> Staff:
    """Deserialise a parquet row back to a Staff object."""
    def _load(val: Any) -> list:
        if val is None:
            return []
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, ValueError):
                return []
        if isinstance(val, list):
            return val
        return []

    return Staff(
        company=str(row["company"] or ""),
        name=str(row["name"] or ""),
        title=row.get("title") or None,
        profile_url=str(row["profile_url"] or ""),
        location=row.get("location") or None,
        education=[Education(**e) for e in _load(row.get("education"))],
        experiences=[Experience(**e) for e in _load(row.get("experiences"))],
        skills=_load(row.get("skills")),
        email=row.get("email") or None,
        contactable=bool(row.get("contactable", False)),
        source=str(row.get("source") or "staffspy"),
    )


def write_staff_parquet(staff: list[Staff], path: Path) -> None:
    """Write a list of Staff objects to a parquet file (atomic via temp file).

    Uses pyarrow directly (not pandas' to_parquet engine) to avoid the
    ArrowKeyError double-registration bug in pandas≥2.3 + pyarrow≥24.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.parquet")
    rows = [staff_to_row(s) for s in staff]
    if not rows:
        schema = pa.schema(
            [
                ("company", pa.string()),
                ("name", pa.string()),
                ("title", pa.string()),
                ("profile_url", pa.string()),
                ("location", pa.string()),
                ("education", pa.string()),
                ("experiences", pa.string()),
                ("skills", pa.string()),
                ("email", pa.string()),
                ("contactable", pa.bool_()),
                ("source", pa.string()),
            ]
        )
        table = pa.table(
            {f.name: pa.array([], type=f.type) for f in schema}, schema=schema
        )
    else:
        # Build column-oriented dict; cast booleans explicitly
        keys = list(rows[0].keys())
        data: dict[str, list] = {k: [r.get(k) for r in rows] for k in keys}
        # Ensure 'contactable' is a proper bool array
        data["contactable"] = [bool(v) for v in data.get("contactable", [])]
        table = pa.table(data)
    pq.write_table(table, str(tmp))
    tmp.replace(path)


def read_staff_parquet(path: Path) -> list[Staff]:
    """Read staff.parquet and return a list of Staff objects.

    Uses pyarrow directly (not pandas' read_parquet) for the same reason as
    write_staff_parquet.
    """
    import pyarrow.parquet as pq

    table = pq.read_table(str(path))
    # Convert to row-oriented Python dicts without going through pandas
    col_dict = table.to_pydict()
    n = table.num_rows
    rows = [{k: col_dict[k][i] for k in col_dict} for i in range(n)]
    return [row_to_staff(row) for row in rows]


# ---------------------------------------------------------------------------
# StaffSpy normalisation helpers
# ---------------------------------------------------------------------------


def _safe_load_list(val: Any) -> list:
    if val is None:
        return []
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return []
    if isinstance(val, list):
        return val
    return []


def _normalise_skills(skills: Any) -> list[str]:
    items = _safe_load_list(skills)
    result: list[str] = []
    for s in items:
        if isinstance(s, str):
            result.append(s.strip())
        elif isinstance(s, dict):
            v = s.get("name") or s.get("skill") or ""
            if v:
                result.append(str(v).strip())
        elif hasattr(s, "name"):
            result.append(str(s.name).strip())
    return [s for s in result if s]


def _normalise_education(edu: Any) -> Education:
    if isinstance(edu, dict):
        return Education(
            school=edu.get("school") or edu.get("name") or "",
            degree=edu.get("degree_name") or edu.get("degree"),
            field=edu.get("field_of_study") or edu.get("field"),
            years=edu.get("date_range") or edu.get("years"),
        )
    return Education(
        school=getattr(edu, "school", "") or getattr(edu, "name", "") or "",
        degree=getattr(edu, "degree_name", None),
        field=getattr(edu, "field_of_study", None),
        years=getattr(edu, "date_range", None),
    )


def _normalise_experience(exp: Any) -> Experience:
    if isinstance(exp, dict):
        return Experience(
            company=exp.get("company") or "",
            title=exp.get("title") or exp.get("role"),
            years=exp.get("date_range") or exp.get("years"),
        )
    return Experience(
        company=getattr(exp, "company", "") or "",
        title=getattr(exp, "title", None),
        years=getattr(exp, "date_range", None) or getattr(exp, "years", None),
    )


def _df_row_to_staff(row: Any, company: str) -> Staff:
    """Convert a single StaffSpy DataFrame row to a Staff contract object."""
    r = dict(row) if hasattr(row, "items") else {k: getattr(row, k, None) for k in row._fields} \
        if hasattr(row, "_fields") else {}

    def _g(key: str, *fallbacks: str) -> Any:
        for k in (key, *fallbacks):
            v = r.get(k)
            if v is not None and str(v).strip() not in ("", "nan", "None"):
                return v
        return None

    return Staff(
        company=company,
        name=str(_g("name", "full_name") or ""),
        title=_g("headline", "title", "job_title"),
        profile_url=str(_g("profile_link", "linkedin_profile_url", "profile_url") or ""),
        location=_g("location"),
        education=[
            _normalise_education(e)
            for e in _safe_load_list(_g("educations", "education"))
        ],
        experiences=[
            _normalise_experience(e)
            for e in _safe_load_list(_g("experiences"))
        ],
        skills=_normalise_skills(_g("skills")),
        email=_g("email"),
        contactable=bool(_g("is_connection", "connection", "is_1st_connection") or False),
        source="staffspy",
    )


# ---------------------------------------------------------------------------
# Daily ceiling check
# ---------------------------------------------------------------------------


def _is_at_ceiling_today(state: State, company: str, ceiling: int) -> bool:
    """Return True if this company was already enumerated today at or above ceiling."""
    with state._conn() as conn:
        row = conn.execute(
            "SELECT enumerated_at, n_staff FROM companies_enumerated WHERE company=?",
            (company,),
        ).fetchone()
    if not row:
        return False
    enumerated = datetime.fromisoformat(row["enumerated_at"])
    today = datetime.now(timezone.utc).date()
    return enumerated.date() == today and int(row["n_staff"] or 0) >= ceiling


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def fetch_staff(cfg: Config, companies: list[str], logger: RunLogger) -> int:
    """Enumerate staff for *companies* using StaffSpy and write data/staff.parquet.

    Args:
        cfg:       Loaded pipeline config.
        companies: Company names to enumerate (must be non-empty; requires operator approval).
        logger:    RunLogger for structured event output.

    Returns:
        Total number of Staff records written.

    Raises:
        StaffFetchCeilingError: If a company was already enumerated today at the ceiling.
    """
    provider = cfg.get("people.provider", "staffspy")

    # --- NO-OP stub for the interactive MCP path ---
    if provider == "linkedin_mcp":
        logger.event(
            "fetch_staff",
            action="noop",
            reason="people.provider=linkedin_mcp; use the MCP people layer for interactive lookups",
            count_out=0,
            company_count=0,
        )
        return 0

    # --- StaffSpy path (provider == "staffspy" or "both") ---
    try:
        import staffspy  # noqa: F401 — lazy import; fails loudly if not installed
        from staffspy import LinkedInSession
    except ImportError as exc:
        raise ImportError(
            "staffspy not installed.  Run:  uv pip install '.[people]'"
        ) from exc

    ceiling: int = int(cfg.get("people.staffspy.max_profiles_per_company_per_day", 75))
    delay: float = float(cfg.get("people.staffspy.inter_request_delay_sec", 8))
    session_file: str = str(cfg.get("people.staffspy.session_file", "session.pkl"))
    captcha_solver: str = str(cfg.get("people.staffspy.captcha_solver", "none"))

    # Never pass a proxy to LinkedInSession (hard rule; checked by tests).
    # Any future refactor MUST NOT add proxy/proxies kwargs here.
    import os
    solver_key = os.environ.get("CAPTCHA_SOLVER_API_KEY")
    session_kwargs: dict[str, Any] = {"session_file": session_file}
    if captcha_solver not in ("none", "", None):
        session_kwargs["captcha_solver"] = captcha_solver
        if solver_key:
            session_kwargs["solver_api_key"] = solver_key

    state = State(cfg.sqlite_path)
    data_dir = cfg.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = data_dir / "staff.parquet"

    # Load existing parquet rows to append to them across multiple company calls
    existing: list[Staff] = []
    if parquet_path.exists():
        existing = read_staff_parquet(parquet_path)

    all_staff: list[Staff] = list(existing)
    total_new = 0
    companies_fetched = 0

    with logger.timed("fetch_staff", companies=companies):
        for company in companies:
            # Hard daily ceiling check
            if _is_at_ceiling_today(state, company, ceiling):
                raise StaffFetchCeilingError(
                    f"Daily ceiling of {ceiling} profiles already reached for {company!r}. "
                    "Wait until tomorrow or raise people.staffspy.max_profiles_per_company_per_day."
                )

            session = LinkedInSession(**session_kwargs)
            df = session.scrape_staff(
                company_name=company,
                max_results=ceiling,
                extra_profile_data=True,
            )

            if df is None or len(df) == 0:
                _LOG.warning("StaffSpy returned 0 results for %r", company)
                state.record_company(company, n_staff=0)
                companies_fetched += 1
                continue

            # Hard ceiling: truncate if StaffSpy somehow exceeded max_results
            if len(df) > ceiling:
                _LOG.warning(
                    "StaffSpy returned %d rows for %r (ceiling %d) — truncating",
                    len(df), company, ceiling,
                )
                df = df.iloc[:ceiling]

            new_staff: list[Staff] = []
            for _, row in df.iterrows():
                s = _df_row_to_staff(row, company)
                if s.profile_url:
                    new_staff.append(s)

            state.record_company(company, n_staff=len(new_staff))
            all_staff.extend(new_staff)
            total_new += len(new_staff)
            companies_fetched += 1

            if delay > 0 and company != companies[-1]:
                time.sleep(delay)

    # Write (overwrite) the combined parquet
    write_staff_parquet(all_staff, parquet_path)

    logger.event(
        "fetch_staff",
        count_out=total_new,
        company_count=companies_fetched,
        parquet=str(parquet_path),
    )
    return total_new
