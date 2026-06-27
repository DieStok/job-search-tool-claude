"""Pipeline MCP server (AC-030) — exposes the pipeline to Claude Desktop as tools.

Read tools are un-gated. Account-risk / credit-spend tools (`run_staffspy`,
`enrich_person`) are GATED: they refuse to act unless called with `confirm=True`. This is
the in-server human-in-the-loop gate; additionally, set these to "Approval required" in
Claude Desktop (see docs/CLAUDE_DESKTOP.md). `draft_outreach` never sends.

Run:  python -m lcp.mcp_server            # stdio server for Claude Desktop
      python -m lcp.mcp_server --selfcheck # list tools + gating, exit 0 (no server)
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import config as _config
from . import runlog
from .outreach import draft_outreach as _draft
from .state import State

# tool name -> gated? (the confirmation contract; used by selfcheck + tests)
TOOL_REGISTRY: dict[str, bool] = {
    "get_shortlist": False,
    "list_people_to_meet": False,
    "run_jobspy": False,
    "score_people": False,
    "run_staffspy": True,       # account risk
    "enrich_person": True,      # credit spend
    "draft_outreach": False,    # never sends
    "mark_contacted": False,
}
GATED = {k for k, v in TOOL_REGISTRY.items() if v}

CONFIRM_MSG = (
    "Confirmation required: this action {what}. Re-call with confirm=true to proceed "
    "(in Claude Desktop this tool should be set to 'Approval required')."
)


def load_cfg():
    return _config.load_config(os.environ.get("LCP_CONFIG"))


def _read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _stage(module: str, func: str, *args):
    mod = importlib.import_module(f"lcp.{module}")
    return getattr(mod, func)(*args)


# ---- tool implementations (cfg-explicit, directly unit-testable) -------------
def impl_get_shortlist(cfg) -> list:
    return _read_json(cfg.data_dir / "shortlist.json", [])


def impl_list_people_to_meet(cfg) -> list:
    return _read_json(cfg.data_dir / "people_to_meet.json", [])


def impl_run_jobspy(cfg, logger) -> dict:
    fetched = _stage("fetch_jobs", "fetch_jobs", cfg, logger)
    shortlisted = _stage("rank_jobs", "rank_jobs", cfg, logger)
    return {"fetched": fetched, "shortlisted": shortlisted}


def impl_score_people(cfg, logger) -> int:
    return _stage("score_people", "score_people", cfg, logger)


def impl_run_staffspy(cfg, logger, company: str, confirm: bool = False):
    if not confirm:
        return {"status": "confirmation_required",
                "message": CONFIRM_MSG.format(what=f"enumerates staff at {company} (account risk)")}
    n = _stage("fetch_staff", "fetch_staff", cfg, [company], logger)
    return {"status": "ok", "staff_fetched": n}


def impl_enrich_person(cfg, logger, profile_url: str, confirm: bool = False):
    if not confirm:
        return {"status": "confirmation_required",
                "message": CONFIRM_MSG.format(what="spends an enrichment lookup (may cost a credit)")}
    contact = _stage("enrich", "enrich_person", cfg, profile_url, logger)
    return {"status": "ok", "contact": contact.model_dump() if hasattr(contact, "model_dump") else contact}


def impl_draft_outreach(cfg, logger, profile_url: str) -> dict:
    people = impl_list_people_to_meet(cfg)
    match = next((p for p in people if p.get("profile_url") == profile_url), None)
    if not match:
        return {"status": "not_found", "message": f"{profile_url} not in people_to_meet.json"}
    return _draft(cfg, match, logger).model_dump()


def impl_mark_contacted(cfg, profile_url: str, status: str = "contacted") -> dict:
    st = State(cfg.sqlite_path)
    st.record_person(profile_url, status=status)
    return {"status": "ok", "profile_url": profile_url, "contact_status": status}


# ---- server assembly --------------------------------------------------------
def build_server(cfg=None) -> FastMCP:
    cfg = cfg or load_cfg()
    logger = runlog.RunLogger(cfg.run_log_dir)
    mcp = FastMCP("linkedin-coffee-pipeline")

    @mcp.tool()
    def get_shortlist() -> list:
        """Read the ranked job shortlist (shortlist.json)."""
        return impl_get_shortlist(cfg)

    @mcp.tool()
    def list_people_to_meet() -> list:
        """Read the warmth-ranked people to meet (people_to_meet.json)."""
        return impl_list_people_to_meet(cfg)

    @mcp.tool()
    def run_jobspy() -> dict:
        """Fetch fresh jobs and rank them into a shortlist."""
        return impl_run_jobspy(cfg, logger)

    @mcp.tool()
    def score_people() -> int:
        """(Re)compute warmth scores from staff + your profile -> people_to_meet.json."""
        return impl_score_people(cfg, logger)

    @mcp.tool()
    def run_staffspy(company: str, confirm: bool = False) -> dict:
        """GATED: enumerate staff at a company (account risk). Needs confirm=True."""
        return impl_run_staffspy(cfg, logger, company, confirm)

    @mcp.tool()
    def enrich_person(profile_url: str, confirm: bool = False) -> dict:
        """GATED: find a contact path for a person (may spend a credit). Needs confirm=True."""
        return impl_enrich_person(cfg, logger, profile_url, confirm)

    @mcp.tool()
    def draft_outreach(profile_url: str) -> dict:
        """Draft a personalized coffee-chat message for a person. Never sends."""
        return impl_draft_outreach(cfg, logger, profile_url)

    @mcp.tool()
    def mark_contacted(profile_url: str, status: str = "contacted") -> dict:
        """Record that you reached out to someone (dedup; prevents re-drafting)."""
        return impl_mark_contacted(cfg, profile_url, status)

    return mcp


def selfcheck() -> int:
    print("linkedin-coffee-pipeline MCP — registered tools:")
    for name, gated in TOOL_REGISTRY.items():
        print(f"  - {name}{'  [GATED: needs confirm=True]' if gated else ''}")
    # build the server to confirm registration actually works
    build_server()
    print(f"OK: {len(TOOL_REGISTRY)} tools, {len(GATED)} gated ({', '.join(sorted(GATED))})")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--selfcheck" in argv:
        return selfcheck()
    build_server().run()  # stdio
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
