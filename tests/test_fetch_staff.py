"""D3 / AC-020 — fetch_staff: StaffSpy wrapper, own-IP-only, daily ceiling.

Tests mock StaffSpy entirely (it is an optional install) via sys.modules injection.
Assertions:
  - provider=linkedin_mcp → NO-OP stub (short-circuits before StaffSpy is touched)
  - daily ceiling enforced: record_company sets n_staff≥ceiling today → raises StaffFetchCeilingError
  - returned parquet matches the Staff contract
  - StaffSpy is NEVER called with a proxy argument
  - run-log event has stage="fetch_staff", count_out, company_count
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from lcp.config import load_config
from lcp.contracts import Staff
from lcp.runlog import RunLogger
from lcp.state import State

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[1]
GOLDEN_STAFF = json.loads((REPO / "eval/golden/staff_sample.json").read_text())


def _make_staffspy_df(rows: list[dict]) -> pd.DataFrame:
    """Build a DataFrame that mimics what StaffSpy v0.2.25 returns."""
    records = []
    for r in rows:
        records.append(
            {
                "name": r["name"],
                "headline": r["title"],
                "profile_link": r["profile_url"],
                "location": r["location"],
                "skills": r["skills"],
                "experiences": [
                    {"company": e["company"], "title": e.get("title"), "date_range": e.get("years", "")}
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
    return pd.DataFrame(records)


def _mock_staffspy_module(df: pd.DataFrame) -> MagicMock:
    """Return a mock staffspy module whose LinkedInSession.scrape_staff returns df."""
    mock_mod = MagicMock()
    mock_session = MagicMock()
    mock_session.scrape_staff.return_value = df
    mock_mod.LinkedInSession.return_value = mock_session
    return mock_mod, mock_session


def _cfg(tmp_path: Path, provider: str = "staffspy", ceiling: int = 75) -> Any:
    """Load the example config, override a few fields for tests."""
    cfg = load_config(REPO / "config/config.example.yaml")
    cfg.raw.setdefault("people", {}).setdefault("staffspy", {})
    cfg.raw["people"]["provider"] = provider
    cfg.raw["people"]["staffspy"]["max_profiles_per_company_per_day"] = ceiling
    cfg.raw["people"]["staffspy"]["inter_request_delay_sec"] = 0  # no sleep in tests
    cfg.raw["people"]["staffspy"]["session_file"] = str(tmp_path / "session.pkl")
    cfg.raw["people"]["staffspy"]["captcha_solver"] = "none"
    cfg.raw["meta"]["data_dir"] = str(tmp_path / "data")
    cfg.raw["state"]["sqlite_path"] = str(tmp_path / "state.sqlite")
    cfg.raw["observability"]["run_log_dir"] = str(tmp_path / "runs")
    return cfg


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_provider_linkedin_mcp_is_noop(tmp_path, capsys):
    """If people.provider=linkedin_mcp, fetch_staff must be a NO-OP stub (never calls StaffSpy)."""
    cfg = _cfg(tmp_path, provider="linkedin_mcp")
    logger = RunLogger(tmp_path / "runs")

    # Inject a sentinel so any import of staffspy would raise
    with patch.dict(sys.modules, {"staffspy": None}):
        from lcp.fetch_staff import fetch_staff

        n = fetch_staff(cfg, ["Acme"], logger)

    assert n == 0, "NO-OP stub must return 0"
    # No parquet written
    parquet_path = Path(cfg.raw["meta"]["data_dir"]) / "staff.parquet"
    assert not parquet_path.exists(), "NO-OP must not write parquet"


def test_ceiling_raises_when_already_reached(tmp_path):
    """StaffFetchCeilingError raised when this company was already enumerated at ceiling today."""
    from lcp.fetch_staff import StaffFetchCeilingError, fetch_staff

    cfg = _cfg(tmp_path, provider="staffspy", ceiling=75)
    logger = RunLogger(tmp_path / "runs")

    # Pre-populate state: Acme already at ceiling today
    state = State(cfg.sqlite_path)
    state.record_company("Acme", n_staff=75)  # enumerated_at = now (today)

    df = _make_staffspy_df(GOLDEN_STAFF)
    mock_mod, _ = _mock_staffspy_module(df)

    with patch.dict(sys.modules, {"staffspy": mock_mod}):
        with pytest.raises(StaffFetchCeilingError):
            fetch_staff(cfg, ["Acme"], logger)


def test_staffspy_never_called_with_proxy(tmp_path):
    """StaffSpy must be called without a proxy argument (own IP only)."""
    from lcp.fetch_staff import fetch_staff

    cfg = _cfg(tmp_path, provider="staffspy")
    logger = RunLogger(tmp_path / "runs")

    df = _make_staffspy_df(GOLDEN_STAFF)
    mock_mod, mock_session = _mock_staffspy_module(df)

    with patch.dict(sys.modules, {"staffspy": mock_mod}):
        fetch_staff(cfg, ["TechCorp"], logger)

    # Inspect every call to LinkedInSession constructor: no proxy kwarg
    for call in mock_mod.LinkedInSession.call_args_list:
        args, kwargs = call
        assert "proxy" not in kwargs, "StaffSpy must NEVER receive a proxy"
        assert "proxies" not in kwargs, "StaffSpy must NEVER receive proxies"


def test_parquet_written_and_matches_staff_contract(tmp_path):
    """After fetch, data/staff.parquet exists and every row parses as a Staff object."""
    from lcp.fetch_staff import fetch_staff, read_staff_parquet

    cfg = _cfg(tmp_path, provider="staffspy")
    logger = RunLogger(tmp_path / "runs")

    df = _make_staffspy_df(GOLDEN_STAFF)
    mock_mod, _ = _mock_staffspy_module(df)

    with patch.dict(sys.modules, {"staffspy": mock_mod}):
        n = fetch_staff(cfg, ["TechCorp"], logger)

    parquet_path = Path(cfg.raw["meta"]["data_dir"]) / "staff.parquet"
    assert parquet_path.exists(), "staff.parquet must be written"
    staff_list = read_staff_parquet(parquet_path)
    assert len(staff_list) == len(GOLDEN_STAFF)
    assert n == len(GOLDEN_STAFF)
    # All rows validate against Staff contract
    for s in staff_list:
        assert isinstance(s, Staff)
        assert s.profile_url.startswith("https://")
        assert s.company == "TechCorp"


def test_parquet_preserves_nested_fields(tmp_path):
    """Education and experiences survive the parquet round-trip."""
    from lcp.fetch_staff import fetch_staff, read_staff_parquet

    cfg = _cfg(tmp_path, provider="staffspy")
    logger = RunLogger(tmp_path / "runs")

    df = _make_staffspy_df(GOLDEN_STAFF)
    mock_mod, _ = _mock_staffspy_module(df)

    with patch.dict(sys.modules, {"staffspy": mock_mod}):
        fetch_staff(cfg, ["TechCorp"], logger)

    parquet_path = Path(cfg.raw["meta"]["data_dir"]) / "staff.parquet"
    staff_list = read_staff_parquet(parquet_path)

    alice = next(s for s in staff_list if "alice" in s.profile_url.lower())
    assert any("university of amsterdam" in e.school.lower() for e in alice.education)
    assert any("dataco" in e.company.lower() for e in alice.experiences)
    assert alice.contactable is True


def test_company_recorded_in_state(tmp_path):
    """State.record_company is called for the enumerated company."""
    from lcp.fetch_staff import fetch_staff

    cfg = _cfg(tmp_path, provider="staffspy")
    logger = RunLogger(tmp_path / "runs")

    df = _make_staffspy_df(GOLDEN_STAFF)
    mock_mod, _ = _mock_staffspy_module(df)

    state = State(cfg.sqlite_path)
    assert not state.is_company_enumerated("TechCorp")

    with patch.dict(sys.modules, {"staffspy": mock_mod}):
        fetch_staff(cfg, ["TechCorp"], logger)

    assert state.is_company_enumerated("TechCorp")


def test_runlog_event_emitted(tmp_path):
    """Run-log contains a fetch_staff event with count_out and company_count."""
    import json as _json

    from lcp.fetch_staff import fetch_staff

    cfg = _cfg(tmp_path, provider="staffspy")
    logger = RunLogger(tmp_path / "runs")

    df = _make_staffspy_df(GOLDEN_STAFF)
    mock_mod, _ = _mock_staffspy_module(df)

    with patch.dict(sys.modules, {"staffspy": mock_mod}):
        fetch_staff(cfg, ["TechCorp"], logger)

    events = [
        _json.loads(line)
        for line in logger.path.read_text().splitlines()
        if line.strip()
    ]
    stage_events = [e for e in events if e.get("stage") == "fetch_staff"]
    assert stage_events, "fetch_staff event must appear in run-log"
    ev = stage_events[-1]
    assert ev["count_out"] == len(GOLDEN_STAFF)
    assert ev["company_count"] == 1


def test_ceiling_truncates_oversized_result(tmp_path):
    """If StaffSpy somehow returns more rows than the ceiling, we truncate to ceiling."""
    from lcp.fetch_staff import fetch_staff, read_staff_parquet

    ceiling = 2  # set ceiling below len(GOLDEN_STAFF) = 3
    cfg = _cfg(tmp_path, provider="staffspy", ceiling=ceiling)
    logger = RunLogger(tmp_path / "runs")

    df = _make_staffspy_df(GOLDEN_STAFF)  # 3 rows > ceiling=2
    mock_mod, mock_session = _mock_staffspy_module(df)

    with patch.dict(sys.modules, {"staffspy": mock_mod}):
        n = fetch_staff(cfg, ["TechCorp"], logger)

    assert n == ceiling, "Result must be truncated to ceiling"
    parquet_path = Path(cfg.raw["meta"]["data_dir"]) / "staff.parquet"
    staff_list = read_staff_parquet(parquet_path)
    assert len(staff_list) == ceiling
