"""D3 / AC-022 — enrich: waterfall cascade, stop-on-hit, no-paid-spend-without-optin.

Tests mock EnrichmentProvider implementations directly (no network).
Assertions:
  - Cascade order: providers tried in waterfall order
  - Stop-on-hit: once a verified hit is returned, subsequent providers are NOT called
  - No paid spend without opt-in: is_paid provider skipped if allow_paid_spend=False
  - Corporate vs personal email classification
  - API key never logged
  - Cache: second call for same profile_url does NOT call providers
  - null provider always misses
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from lcp.config import load_config
from lcp.contracts import ContactInfo
from lcp.runlog import RunLogger

REPO = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cfg(tmp_path: Path, allow_paid: bool = False, stop_on_verified: bool = True) -> Any:
    cfg = load_config(REPO / "config/config.example.yaml")
    cfg.raw["enrichment"]["allow_paid_spend"] = allow_paid
    cfg.raw["enrichment"]["stop_on_verified"] = stop_on_verified
    cfg.raw["enrichment"]["cache_results"] = True
    cfg.raw["meta"]["data_dir"] = str(tmp_path / "data")
    cfg.raw["state"]["sqlite_path"] = str(tmp_path / "state.sqlite")
    cfg.raw["observability"]["run_log_dir"] = str(tmp_path / "runs")
    return cfg


def _make_mock_provider(
    name: str,
    *,
    is_paid: bool = False,
    returns: ContactInfo | None = None,
) -> MagicMock:
    provider = MagicMock()
    provider.name = name
    provider.is_paid = is_paid
    provider.lookup.return_value = returns
    return provider


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------


def test_cascade_calls_providers_in_order(tmp_path):
    """Providers are tried in the order passed; all called when none returns a hit."""
    from lcp.enrich import enrich_person

    call_order: list[str] = []

    def make_tracker(name: str) -> MagicMock:
        p = _make_mock_provider(name, returns=None)
        def _lookup(url, client):
            call_order.append(name)
            return None
        p.lookup.side_effect = _lookup
        return p

    p1 = make_tracker("first")
    p2 = make_tracker("second")
    p3 = make_tracker("third")

    cfg = _cfg(tmp_path)
    logger = RunLogger(tmp_path / "runs")
    result = enrich_person(
        cfg,
        "https://linkedin.com/in/someone",
        logger,
        _providers=[p1, p2, p3],
    )
    assert call_order == ["first", "second", "third"], "Must call providers in order"
    assert isinstance(result, ContactInfo)


def test_stop_on_verified_hit(tmp_path):
    """After a verified hit, subsequent providers must NOT be called."""
    from lcp.enrich import enrich_person

    p1 = _make_mock_provider(
        "apollo",
        returns=ContactInfo(email="jo@acme.nl", verified=True, provider="apollo"),
    )
    p2 = _make_mock_provider("hunter", returns=None)  # should NOT be called

    cfg = _cfg(tmp_path, stop_on_verified=True)
    logger = RunLogger(tmp_path / "runs")
    result = enrich_person(
        cfg,
        "https://linkedin.com/in/jo",
        logger,
        _providers=[p1, p2],
    )

    assert result.verified is True
    assert result.provider == "apollo"
    p2.lookup.assert_not_called(), "Provider after a verified hit must not be called"


def test_continues_past_unverified_hit(tmp_path):
    """An unverified hit does NOT stop the waterfall when stop_on_verified=True."""
    from lcp.enrich import enrich_person

    p1 = _make_mock_provider(
        "apollo",
        returns=ContactInfo(email="jo@acme.nl", verified=False, provider="apollo"),
    )
    p2 = _make_mock_provider(
        "hunter",
        returns=ContactInfo(email="jo@acme.nl", verified=True, provider="hunter"),
    )

    cfg = _cfg(tmp_path, stop_on_verified=True)
    logger = RunLogger(tmp_path / "runs")
    result = enrich_person(
        cfg,
        "https://linkedin.com/in/jo",
        logger,
        _providers=[p1, p2],
    )

    p2.lookup.assert_called_once(), "Provider p2 must be called when p1 hit is unverified"
    assert result.verified is True
    assert result.provider == "hunter"


def test_no_paid_spend_without_optin(tmp_path):
    """A provider marked is_paid=True is skipped if allow_paid_spend=False."""
    from lcp.enrich import enrich_person

    paid = _make_mock_provider(
        "dropcontact",
        is_paid=True,
        returns=ContactInfo(email="jo@corp.nl", verified=True, provider="dropcontact"),
    )
    free = _make_mock_provider("hunter", returns=None)

    cfg = _cfg(tmp_path, allow_paid=False)
    logger = RunLogger(tmp_path / "runs")
    enrich_person(
        cfg,
        "https://linkedin.com/in/jo",
        logger,
        _providers=[paid, free],
    )

    paid.lookup.assert_not_called(), "Paid provider must be skipped without allow_paid_spend"


def test_paid_provider_used_when_optin(tmp_path):
    """A paid provider IS called when allow_paid_spend=True."""
    from lcp.enrich import enrich_person

    paid = _make_mock_provider(
        "dropcontact",
        is_paid=True,
        returns=ContactInfo(email="jo@corp.nl", verified=True),
    )

    cfg = _cfg(tmp_path, allow_paid=True)
    logger = RunLogger(tmp_path / "runs")
    enrich_person(
        cfg,
        "https://linkedin.com/in/jo",
        logger,
        _providers=[paid],
    )

    paid.lookup.assert_called_once()


def test_corporate_email_classification(tmp_path):
    """is_corporate_email=True for a business domain, False for consumer domains."""
    from lcp.enrich import enrich_person

    corp_provider = _make_mock_provider(
        "apollo",
        returns=ContactInfo(email="jo@acme.nl", verified=True),
    )
    cfg = _cfg(tmp_path)
    logger = RunLogger(tmp_path / "runs")
    result = enrich_person(
        cfg, "https://linkedin.com/in/jo-corp", logger, _providers=[corp_provider]
    )
    assert result.is_corporate_email is True, "acme.nl must be classified corporate"


def test_personal_email_classification(tmp_path):
    """is_corporate_email=False for common free-provider domains."""
    from lcp.enrich import enrich_person

    personal_provider = _make_mock_provider(
        "apollo",
        returns=ContactInfo(email="jo.doe@gmail.com", verified=True),
    )
    cfg = _cfg(tmp_path)
    logger = RunLogger(tmp_path / "runs")
    result = enrich_person(
        cfg, "https://linkedin.com/in/jo-personal", logger, _providers=[personal_provider]
    )
    assert result.is_corporate_email is False, "gmail.com must be classified personal"


def test_cache_prevents_second_provider_call(tmp_path):
    """A cached hit is returned directly; provider.lookup must NOT be called again."""
    from lcp.enrich import enrich_person

    provider = _make_mock_provider(
        "apollo",
        returns=ContactInfo(email="jo@acme.nl", verified=True, provider="apollo"),
    )

    cfg = _cfg(tmp_path)
    logger = RunLogger(tmp_path / "runs")
    url = "https://linkedin.com/in/cached-person"

    # First call: provider is invoked and result is cached
    enrich_person(cfg, url, logger, _providers=[provider])
    assert provider.lookup.call_count == 1

    # Second call: must use cache, NOT call provider again
    enrich_person(cfg, url, logger, _providers=[provider])
    assert provider.lookup.call_count == 1, "Cached result must prevent re-lookup"


def test_null_provider_always_misses(tmp_path):
    """The null provider returns no data (ContactInfo with no email/phone)."""
    from lcp.enrich import NullProvider, enrich_person
    import requests

    null_p = NullProvider()
    result = null_p.lookup("https://linkedin.com/in/x", requests.Session())
    assert result is None, "NullProvider must return None"


def test_returns_empty_contact_info_when_all_miss(tmp_path):
    """When all providers miss, enrich_person returns an empty ContactInfo."""
    from lcp.enrich import enrich_person

    p = _make_mock_provider("hunter", returns=None)
    cfg = _cfg(tmp_path)
    logger = RunLogger(tmp_path / "runs")
    result = enrich_person(
        cfg, "https://linkedin.com/in/unknown", logger, _providers=[p]
    )
    assert isinstance(result, ContactInfo)
    assert result.email is None
    assert result.verified is False


def test_key_not_logged(tmp_path, capsys, monkeypatch):
    """The enrichment run-log must not contain API key values."""
    import os
    from lcp.enrich import enrich_person

    monkeypatch.setenv("APOLLO_API_KEY", "super_secret_key_abc123")
    monkeypatch.setenv("HUNTER_API_KEY", "hunter_secret_xyz789")

    # Use the real Apollo/Hunter providers (they'll miss because keys are fake)
    from lcp.enrich import ApolloProvider, HunterProvider

    cfg = _cfg(tmp_path)
    logger = RunLogger(tmp_path / "runs")
    enrich_person(
        cfg,
        "https://linkedin.com/in/test",
        logger,
        _providers=[ApolloProvider(), HunterProvider()],
    )

    log_text = logger.path.read_text() if logger.path.exists() else ""
    assert "super_secret_key_abc123" not in log_text, "Apollo key must not appear in logs"
    assert "hunter_secret_xyz789" not in log_text, "Hunter key must not appear in logs"


def test_provider_error_does_not_crash_waterfall(tmp_path):
    """A provider that raises must not abort the waterfall — fall through to next provider."""
    from lcp.enrich import enrich_person

    def _raises(url, client):
        raise ConnectionError("network down")

    failing = _make_mock_provider("apollo")
    failing.lookup.side_effect = _raises

    succeeding = _make_mock_provider(
        "hunter",
        returns=ContactInfo(email="jo@acme.nl", verified=True),
    )

    cfg = _cfg(tmp_path)
    logger = RunLogger(tmp_path / "runs")
    result = enrich_person(
        cfg,
        "https://linkedin.com/in/jo",
        logger,
        _providers=[failing, succeeding],
    )
    assert result.email == "jo@acme.nl"
