"""Proxy health check — JobSpy only, never StaffSpy. AC-010.

Exposes a `ProxyBackend` Protocol with >=2 concrete backends selected by
`proxies.backend` in config:

  none        → own IP, no proxies (MVP baseline).
  in_process  → rotate through a static list in config.proxies.in_process.static_list.
  webshare    → build URL from env vars WEBSHARE_PROXY_USER/PASS/HOST.
  scrapoxy    → (passthrough to none for now; scrapoxy is a self-hosted gateway).
  free_pool   → (passthrough to none; datacenter IPs are blocked by LinkedIn on arrival).

`check_proxies` probes each candidate against a real request to
`proxies.check_target`, keeps unblocked ones, and writes data/good_proxies.json.

HARD RULE: This module is JobSpy-only.  StaffSpy must NEVER use a proxy
(see §6 of GOAL.md).  The proxy list lives in data/good_proxies.json and is
consumed only by fetch_jobs.py.  StaffSpy's fetch_staff.py must not read it.

Network calls are hidden behind the module-level `_probe` function so tests
can patch it without touching the HTTP layer.
"""

from __future__ import annotations

import json
import os
from typing import Protocol, runtime_checkable

import requests

from .config import Config
from .runlog import RunLogger


# ---------------------------------------------------------------------------
# Backend protocol + implementations
# ---------------------------------------------------------------------------

@runtime_checkable
class ProxyBackend(Protocol):
    """Interface all proxy backends implement."""

    def get_candidates(self, cfg: Config) -> list[str]:
        """Return a list of proxy URLs to probe (empty = use own IP)."""
        ...  # pragma: no cover


class NoneBackend:
    """Own-IP (no proxies). The MVP baseline — JobSpy runs directly."""

    def get_candidates(self, cfg: Config) -> list[str]:  # noqa: ARG002
        return []


class InProcessBackend:
    """Round-robin through a static proxy list kept in config."""

    def get_candidates(self, cfg: Config) -> list[str]:
        raw = cfg.get("proxies.in_process.static_list") or []
        return list(raw)


class WebshareBackend:
    """Webshare rotating residential proxy.

    Credentials from environment variables (NEVER stored in config):
      WEBSHARE_PROXY_USER  — Webshare username
      WEBSHARE_PROXY_PASS  — Webshare password
      WEBSHARE_PROXY_HOST  — host:port  (e.g. proxy.webshare.io:80)
    """

    def get_candidates(self, cfg: Config) -> list[str]:  # noqa: ARG002
        user = os.environ.get("WEBSHARE_PROXY_USER", "")
        passwd = os.environ.get("WEBSHARE_PROXY_PASS", "")
        host = os.environ.get("WEBSHARE_PROXY_HOST", "")
        if not (user and passwd and host):
            return []
        return [f"http://{user}:{passwd}@{host}"]


def _get_backend(cfg: Config) -> ProxyBackend:
    """Return the backend instance for the configured backend name."""
    backend = cfg.get("proxies.backend", "none")
    match backend:
        case "webshare":
            return WebshareBackend()
        case "in_process":
            return InProcessBackend()
        case _:
            # none / free_pool / scrapoxy all fall back to own-IP for now.
            return NoneBackend()


# ---------------------------------------------------------------------------
# Probe function (module-level so tests can patch it)
# ---------------------------------------------------------------------------

_CHECK_URLS: dict[str, str] = {
    "linkedin": "https://www.linkedin.com/jobs/",
}
_DEFAULT_CHECK_URL = "https://httpbin.org/ip"


def _probe(proxy_url: str | None, check_target: str, session: requests.Session) -> bool:
    """Return True if the proxy is not blocked for the given check_target board.

    Args:
        proxy_url:    Full proxy URL (e.g. ``http://user:pass@host:port``) or None.
        check_target: Board name key from ``_CHECK_URLS`` (e.g. "linkedin").
        session:      Requests Session to use for the probe request.

    Returns:
        True if the request returned HTTP 200; False on any error or non-200.
    """
    url = _CHECK_URLS.get(check_target, _DEFAULT_CHECK_URL)
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    try:
        resp = session.get(url, proxies=proxies, timeout=12, allow_redirects=True)
        return resp.status_code < 400
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_proxies(cfg: Config, logger: RunLogger, *, http_session: requests.Session | None = None) -> int:
    """Probe proxy candidates and write data/good_proxies.json.

    Reads the configured backend, calls ``get_candidates``, probes each one,
    and keeps those that receive a non-blocked response.

    The ``none`` backend skips probing entirely (own-IP is always valid).

    Args:
        cfg:          Pipeline config (proxy backend + check_target from here).
        logger:       RunLogger to record the ``proxy_check`` event.
        http_session: Optional requests.Session for DI in tests (real session used if None).

    Returns:
        Number of good (unblocked) proxies found.
    """
    backend_name = cfg.get("proxies.backend", "none")
    backend = _get_backend(cfg)
    candidates = backend.get_candidates(cfg)
    check_target = cfg.get("proxies.check_target", "linkedin")

    good: list[str] = []

    if candidates:
        session = http_session or requests.Session()
        for proxy_url in candidates:
            if _probe(proxy_url, check_target, session):
                good.append(proxy_url)

    # Write result (always, even for none-backend so downstream consumers get [])
    out_path = cfg.data_dir / "good_proxies.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(good), encoding="utf-8")

    logger.event(
        "proxy_check",
        backend=backend_name,
        count_in=len(candidates),
        count_out=len(good),
    )
    return len(good)
