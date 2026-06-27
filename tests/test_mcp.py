"""D4 / AC-030 — MCP tools registered + risky tools gated behind confirm."""

from __future__ import annotations

import json
import subprocess
import sys
from unittest import mock

from lcp import mcp_server as m
from lcp.config import load_config
from lcp.paths import repo_root

CFG = load_config(repo_root() / "config" / "config.example.yaml")


def test_all_eight_tools_registered():
    expected = {"get_shortlist", "list_people_to_meet", "run_jobspy", "score_people",
                "run_staffspy", "enrich_person", "draft_outreach", "mark_contacted"}
    assert set(m.TOOL_REGISTRY) == expected


def test_gated_set():
    assert m.GATED == {"run_staffspy", "enrich_person"}


def test_run_staffspy_blocked_without_confirm():
    with mock.patch.object(m, "_stage") as stage:
        out = m.impl_run_staffspy(CFG, None, "TechCorp", confirm=False)
        assert out["status"] == "confirmation_required"
        stage.assert_not_called()                 # the side effect MUST NOT fire


def test_run_staffspy_runs_with_confirm():
    with mock.patch.object(m, "_stage", return_value=7) as stage:
        out = m.impl_run_staffspy(CFG, None, "TechCorp", confirm=True)
        assert out["status"] == "ok" and out["staff_fetched"] == 7
        stage.assert_called_once()


def test_enrich_person_blocked_without_confirm():
    with mock.patch.object(m, "_stage") as stage:
        out = m.impl_enrich_person(CFG, None, "https://li/alice", confirm=False)
        assert out["status"] == "confirmation_required"
        stage.assert_not_called()


def test_build_server_registers_without_error():
    srv = m.build_server(CFG)
    assert srv is not None


def test_selfcheck_cli_exits_zero_and_lists_gated():
    r = subprocess.run([sys.executable, "-m", "lcp.mcp_server", "--selfcheck"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "run_staffspy" in r.stdout and "GATED" in r.stdout


def test_draft_outreach_tool_reads_people_file(tmp_path, monkeypatch):
    # point data_dir at a temp people_to_meet.json
    people = [{"name": "Alice", "company": "TechCorp", "profile_url": "https://li/alice",
               "why": ["shared school: UvA"], "warmth_score": 0.9, "contact_status": "new"}]
    (tmp_path / "people_to_meet.json").write_text(json.dumps(people), encoding="utf-8")
    cfg = load_config(repo_root() / "config" / "config.example.yaml")
    monkeypatch.setattr(type(cfg), "data_dir", property(lambda self: tmp_path))
    out = m.impl_draft_outreach(cfg, None, "https://li/alice")
    assert out["sent"] is False and "UvA" in out["body"]
