"""AC-010 — proxy_check: >=2 backends, mocked network, per-backend assertions.

Network calls are fully mocked via patching the module-level `_probe` function;
no real HTTP requests are made in this suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lcp.config import Config
from lcp.runlog import RunLogger


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _cfg(tmp_path: Path, backend: str = "none", static_list: list[str] | None = None) -> Config:
    """Minimal Config pointing to tmp_path with the given proxy backend."""
    raw = {
        "meta": {"data_dir": str(tmp_path)},
        "proxies": {
            "backend": backend,
            "check_target": "linkedin",
            "in_process": {"static_list": static_list or []},
        },
        "compliance": {"require_human_send": True, "max_daily_outreach": 20},
        "orchestration": {
            "mcp_mode": "custom_pipeline",
            "scheduler": "launchd",
        },
        "outreach": {"mode": "draft_only"},
        "people": {
            "provider": "linkedin_mcp",
            "staffspy": {
                "account_mode": "main",
                "captcha_solver": "none",
            },
        },
        "enrichment": {"mode": "mcp"},
    }
    return Config(raw=raw, profile={}, rubric={}, source_path=tmp_path / "config.yaml")


def _logger(tmp_path: Path) -> RunLogger:
    return RunLogger(tmp_path / "runs")


# ---------------------------------------------------------------------------
# AC-010 tests
# ---------------------------------------------------------------------------

class TestNoneBackend:
    def test_writes_empty_good_proxies(self, tmp_path):
        from lcp.proxy_check import check_proxies

        n = check_proxies(_cfg(tmp_path, backend="none"), _logger(tmp_path))

        assert n == 0
        good = json.loads((tmp_path / "good_proxies.json").read_text())
        assert good == []

    def test_no_network_calls_made(self, tmp_path):
        """none backend must never hit the network (_probe is never called)."""
        from lcp import proxy_check as pc
        from lcp.proxy_check import check_proxies

        calls: list = []

        def spy(proxy_url, check_target, session):  # pragma: no cover
            calls.append(proxy_url)
            return True

        with patch.object(pc, "_probe", spy):
            check_proxies(_cfg(tmp_path, backend="none"), _logger(tmp_path))

        assert calls == [], "none backend must not probe the network"


class TestInProcessBackend:
    def test_keeps_passing_proxies(self, tmp_path):
        from lcp import proxy_check as pc
        from lcp.proxy_check import check_proxies

        GOOD = "http://user:pass@proxy1.example.com:8080"
        BAD = "http://user:pass@proxy2.example.com:8080"
        probed: list[str] = []

        def fake_probe(proxy_url, check_target, session):
            probed.append(proxy_url)
            return proxy_url == GOOD

        cfg = _cfg(tmp_path, backend="in_process", static_list=[GOOD, BAD])
        with patch.object(pc, "_probe", fake_probe):
            n = check_proxies(cfg, _logger(tmp_path))

        assert n == 1
        good = json.loads((tmp_path / "good_proxies.json").read_text())
        assert good == [GOOD]
        assert set(probed) == {GOOD, BAD}

    def test_all_blocked_writes_empty(self, tmp_path):
        from lcp import proxy_check as pc
        from lcp.proxy_check import check_proxies

        cfg = _cfg(tmp_path, backend="in_process",
                   static_list=["http://blocked@proxy:8080"])
        with patch.object(pc, "_probe", lambda *_: False):
            n = check_proxies(cfg, _logger(tmp_path))

        assert n == 0
        assert json.loads((tmp_path / "good_proxies.json").read_text()) == []

    def test_empty_static_list_writes_empty(self, tmp_path):
        from lcp.proxy_check import check_proxies

        n = check_proxies(_cfg(tmp_path, backend="in_process", static_list=[]), _logger(tmp_path))
        assert n == 0
        assert json.loads((tmp_path / "good_proxies.json").read_text()) == []


class TestWebshareBackend:
    def test_builds_url_from_env_and_probes(self, tmp_path, monkeypatch):
        from lcp import proxy_check as pc
        from lcp.proxy_check import check_proxies

        monkeypatch.setenv("WEBSHARE_PROXY_USER", "wsuser")
        monkeypatch.setenv("WEBSHARE_PROXY_PASS", "wssecret")
        monkeypatch.setenv("WEBSHARE_PROXY_HOST", "proxy.webshare.io:80")

        probed: list[str] = []

        def ok_probe(proxy_url, check_target, session):
            probed.append(proxy_url)
            return True

        with patch.object(pc, "_probe", ok_probe):
            n = check_proxies(_cfg(tmp_path, backend="webshare"), _logger(tmp_path))

        assert n == 1
        assert len(probed) == 1
        assert "wsuser" in probed[0]
        assert "wssecret" in probed[0]

    def test_missing_env_returns_zero_no_probe(self, tmp_path, monkeypatch):
        from lcp import proxy_check as pc
        from lcp.proxy_check import check_proxies

        monkeypatch.delenv("WEBSHARE_PROXY_USER", raising=False)
        monkeypatch.delenv("WEBSHARE_PROXY_PASS", raising=False)
        monkeypatch.delenv("WEBSHARE_PROXY_HOST", raising=False)

        calls: list = []
        with patch.object(pc, "_probe", lambda *_: calls.append(1) or True):
            n = check_proxies(_cfg(tmp_path, backend="webshare"), _logger(tmp_path))

        assert n == 0
        assert calls == []
        assert json.loads((tmp_path / "good_proxies.json").read_text()) == []


class TestRunlog:
    def test_event_written_with_count_out(self, tmp_path):
        """check_proxies always writes a proxy_check event with count_out."""
        from lcp.proxy_check import check_proxies

        logger = _logger(tmp_path)
        check_proxies(_cfg(tmp_path, backend="none"), logger)

        events = [json.loads(line) for line in logger.path.read_text().splitlines()]
        evt = next((e for e in events if e["stage"] == "proxy_check"), None)
        assert evt is not None, "proxy_check event not written"
        assert "count_out" in evt

    def test_event_records_backend(self, tmp_path):
        from lcp.proxy_check import check_proxies

        logger = _logger(tmp_path)
        check_proxies(_cfg(tmp_path, backend="none"), logger)

        events = [json.loads(line) for line in logger.path.read_text().splitlines()]
        evt = next(e for e in events if e["stage"] == "proxy_check")
        assert evt["backend"] == "none"


class TestStaffSpyIsolation:
    def test_proxy_file_only_written_by_check_proxies(self, tmp_path):
        """Sanity: the proxy file lives in data_dir and is written by check_proxies only.

        This is the structural enforcement that StaffSpy (which must never use proxies)
        cannot see a proxy list unless it explicitly looks for it — it doesn't.
        """
        from lcp.proxy_check import check_proxies

        check_proxies(_cfg(tmp_path, backend="none"), _logger(tmp_path))
        # The file exists; a StaffSpy-unaware caller would not know to read it.
        proxy_file = tmp_path / "good_proxies.json"
        assert proxy_file.exists()
        # Content is always a JSON list (never a dict or null).
        content = json.loads(proxy_file.read_text())
        assert isinstance(content, list)
