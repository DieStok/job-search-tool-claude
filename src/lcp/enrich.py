"""D3 / AC-022 — Enrichment waterfall: free-tier-first cascade to a contact path.

Architecture:
  - `EnrichmentProvider` — abstract base; each provider implements `lookup()`.
  - Concrete providers: `ApolloProvider`, `HunterProvider`, `ProspeoProvider`,
    `NullProvider` (always misses).  Keys read exclusively from env vars.
  - `enrich_person()` — the public entry point; cascades providers, stops on a
    verified hit when `stop_on_verified=True`, skips paid providers without
    `allow_paid_spend=True`, caches results to data/contacts/<hash>.json.
  - Injectable `_providers` and `_client` params enable full test isolation.

Compliance hard rules (never weaken):
  - API keys are NEVER passed to the logger.
  - A provider with `is_paid=True` is skipped unless cfg.enrichment.allow_paid_spend=True.
  - `is_corporate_email` is set on every ContactInfo with an email (drives the
    cold-email compliance gate in outreach).

mode=mcp vs mode=python:
  The CLI only dispatches to this module when enrichment.mode==python.  When
  mode==mcp, Claude calls enrichment MCPs directly in-conversation.  Both paths
  exist so operators can switch modes without losing functionality.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path

import requests as _requests

from .config import Config
from .contracts import ContactInfo
from .runlog import RunLogger

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Consumer / free-provider domains (is_corporate_email classification)
# ---------------------------------------------------------------------------

_CONSUMER_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "yahoo.com",
        "yahoo.co.uk",
        "yahoo.fr",
        "yahoo.de",
        "yahoo.nl",
        "yahoo.es",
        "hotmail.com",
        "hotmail.co.uk",
        "hotmail.fr",
        "hotmail.de",
        "hotmail.nl",
        "outlook.com",
        "outlook.nl",
        "outlook.be",
        "live.com",
        "live.nl",
        "live.be",
        "icloud.com",
        "me.com",
        "mac.com",
        "protonmail.com",
        "proton.me",
        "aol.com",
        "gmx.com",
        "gmx.de",
        "gmx.net",
        "web.de",
        "inbox.com",
        "mail.com",
        "zohomail.com",
    }
)


def _classify_email(email: str) -> bool:
    """Return True if the email is a corporate (non-consumer) address."""
    if not email or "@" not in email:
        return False
    domain = email.lower().split("@")[-1].strip()
    return bool(domain) and domain not in _CONSUMER_DOMAINS


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------


class EnrichmentProvider(ABC):
    """Abstract enrichment provider.  Implementations must be side-effect-free
    with respect to keys: keys are read from env vars, never stored or logged.
    """

    name: str = "abstract"
    is_paid: bool = False  # paid providers skipped without allow_paid_spend

    @abstractmethod
    def lookup(
        self,
        profile_url: str,
        client: _requests.Session,
    ) -> ContactInfo | None:
        """Return a ContactInfo if the provider found data, else None.

        Must NEVER log or surface the API key.
        """


# ---------------------------------------------------------------------------
# NullProvider (always misses; useful as the last-resort noop)
# ---------------------------------------------------------------------------


class NullProvider(EnrichmentProvider):
    """No-op provider.  Always returns None.  Safe to list in waterfall."""

    name = "null"
    is_paid = False

    def lookup(self, profile_url: str, client: _requests.Session) -> None:
        return None


# ---------------------------------------------------------------------------
# Apollo (free tier: ~250 emails/day; confirmation-gate recommended for credits)
# ---------------------------------------------------------------------------


class ApolloProvider(EnrichmentProvider):
    """Apollo.io people/match endpoint.  Key: APOLLO_API_KEY env var."""

    name = "apollo"
    is_paid = False  # free tier covers email lookups

    _ENDPOINT = "https://api.apollo.io/v1/people/match"

    def lookup(
        self,
        profile_url: str,
        client: _requests.Session,
    ) -> ContactInfo | None:
        api_key = os.environ.get("APOLLO_API_KEY")
        if not api_key:
            _LOG.debug("APOLLO_API_KEY not set — skipping Apollo")
            return None

        try:
            resp = client.post(
                self._ENDPOINT,
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json={"linkedin_url": profile_url, "reveal_personal_emails": False},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise exc  # caller handles

        person = data.get("person") or {}
        email = person.get("email")
        if not email:
            return None

        verified = str(person.get("email_status", "")).lower() in (
            "verified", "valid", "deliverable"
        )
        return ContactInfo(
            email=email,
            phone=person.get("phone_numbers", [{}])[0].get("sanitized_number") if person.get("phone_numbers") else None,
            verified=verified,
            provider="apollo",
        )


# ---------------------------------------------------------------------------
# Hunter.io (50 credits/month free; email-only)
# ---------------------------------------------------------------------------


class HunterProvider(EnrichmentProvider):
    """Hunter.io Email Finder.  Key: HUNTER_API_KEY env var.

    Note: Hunter doesn't support LinkedIn-URL lookup directly; we use the
    domain-search path if we have a domain, otherwise skip.  For a full
    enrichment chain, pair with Apollo (which does support LinkedIn URL).
    """

    name = "hunter"
    is_paid = False

    _ENDPOINT = "https://api.hunter.io/v2/email-finder"

    def lookup(
        self,
        profile_url: str,
        client: _requests.Session,
    ) -> ContactInfo | None:
        api_key = os.environ.get("HUNTER_API_KEY")
        if not api_key:
            _LOG.debug("HUNTER_API_KEY not set — skipping Hunter")
            return None

        # Extract a domain hint from the profile URL if embedded, otherwise
        # we can't make a useful Hunter query from a bare LinkedIn URL.
        # Hunter is most useful when a company domain is already known; for now
        # return None and let Apollo/Prospeo handle LinkedIn-URL → email.
        _LOG.debug("Hunter: no domain derived from LinkedIn URL alone; skipping")
        return None


# ---------------------------------------------------------------------------
# Prospeo (75 email credits/month free; native MCP at mcp.prospeo.io)
# ---------------------------------------------------------------------------


class ProspeoProvider(EnrichmentProvider):
    """Prospeo LinkedIn URL → email finder.  Key: PROSPEO_API_KEY env var."""

    name = "prospeo"
    is_paid = False

    _ENDPOINT = "https://api.prospeo.io/linkedin-email-finder"

    def lookup(
        self,
        profile_url: str,
        client: _requests.Session,
    ) -> ContactInfo | None:
        api_key = os.environ.get("PROSPEO_API_KEY")
        if not api_key:
            _LOG.debug("PROSPEO_API_KEY not set — skipping Prospeo")
            return None

        try:
            resp = client.post(
                self._ENDPOINT,
                headers={"x-key": api_key, "Content-Type": "application/json"},
                json={"url": profile_url},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise exc

        email = (data.get("response") or {}).get("email")
        if not email:
            return None

        verified = (data.get("response") or {}).get("email_status", "").lower() in (
            "valid", "verified", "deliverable"
        )
        return ContactInfo(
            email=email,
            verified=verified,
            provider="prospeo",
        )


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, type[EnrichmentProvider]] = {
    "apollo": ApolloProvider,
    "hunter": HunterProvider,
    "prospeo": ProspeoProvider,
    "null": NullProvider,
}


def _build_providers(names: list[str]) -> list[EnrichmentProvider]:
    """Instantiate providers from the waterfall name list; skip unknowns with a warning."""
    providers: list[EnrichmentProvider] = []
    for name in names:
        cls = _REGISTRY.get(name.lower())
        if cls is None:
            _LOG.warning("Unknown enrichment provider %r — skipped", name)
            continue
        providers.append(cls())
    return providers


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_path(data_dir: Path, profile_url: str) -> Path:
    key = hashlib.sha256(profile_url.encode()).hexdigest()[:16]
    return data_dir / "contacts" / f"{key}.json"


def _load_cache(data_dir: Path, profile_url: str) -> ContactInfo | None:
    p = _cache_path(data_dir, profile_url)
    if not p.exists():
        return None
    try:
        return ContactInfo.model_validate_json(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(data_dir: Path, profile_url: str, info: ContactInfo) -> None:
    p = _cache_path(data_dir, profile_url)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(info.model_dump_json(), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def enrich_person(
    cfg: Config,
    profile_url: str,
    logger: RunLogger,
    *,
    _providers: list[EnrichmentProvider] | None = None,
    _client: _requests.Session | None = None,
) -> ContactInfo:
    """Cascade through configured enrichment providers and return a ContactInfo.

    Args:
        cfg:         Loaded pipeline config.
        profile_url: LinkedIn profile URL to enrich.
        logger:      RunLogger (API keys are NEVER passed to it).
        _providers:  Inject custom providers (test override; ignores waterfall config).
        _client:     Inject a custom HTTP session (test override).

    Returns:
        ContactInfo (may have no email/phone if all providers missed).
    """
    allow_paid: bool = bool(cfg.get("enrichment.allow_paid_spend", False))
    stop_on_verified: bool = bool(cfg.get("enrichment.stop_on_verified", True))
    cache_enabled: bool = bool(cfg.get("enrichment.cache_results", True))
    data_dir = cfg.data_dir

    # Check cache first
    if cache_enabled:
        cached = _load_cache(data_dir, profile_url)
        if cached is not None:
            logger.event("enrich", action="cache_hit", profile_url=profile_url)
            return cached

    # Build the provider list
    if _providers is not None:
        providers = _providers
    else:
        waterfall_names: list[str] = cfg.get("enrichment.waterfall", [])
        providers = _build_providers(waterfall_names)

    client = _client if _client is not None else _requests.Session()
    best: ContactInfo | None = None

    for provider in providers:
        if provider.is_paid and not allow_paid:
            logger.event(
                "enrich",
                action="skip_paid",
                provider=provider.name,
                reason="allow_paid_spend=false",
            )
            continue

        try:
            hit = provider.lookup(profile_url, client)
        except Exception as exc:  # noqa: BLE001
            # Log the error class and message but NEVER the raw exception repr
            # (which might contain a key embedded in a URL/header trace).
            logger.event(
                "enrich",
                action="provider_error",
                provider=provider.name,
                error_type=type(exc).__name__,
                # Deliberately NOT logging str(exc) to avoid leaking auth headers
            )
            continue

        if hit is None:
            continue

        # Classify email domain
        if hit.email:
            hit = hit.model_copy(
                update={"is_corporate_email": _classify_email(hit.email)}
            )

        # Update best: prefer verified over unverified
        if best is None or (hit.verified and not best.verified):
            best = hit.model_copy(update={"provider": provider.name})

        logger.event(
            "enrich",
            action="hit",
            provider=provider.name,
            has_email=bool(hit.email),
            has_phone=bool(hit.phone),
            verified=hit.verified,
            is_corporate=hit.is_corporate_email,
            # NOTE: email value deliberately NOT logged (personal data)
        )

        if stop_on_verified and hit.verified:
            break

    result = best or ContactInfo()

    if cache_enabled:
        _save_cache(data_dir, profile_url, result)

    logger.event(
        "enrich",
        action="done",
        profile_url=profile_url,
        found=bool(result.email or result.phone),
        verified=result.verified,
        provider=result.provider,
    )
    return result
