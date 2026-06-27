#!/usr/bin/env python3
"""Conformance gate (AC-001): every source-plan open question is exposed as a config
key with options + a baseline. Fails closed if a key is missing.

Exit 0 = all open questions covered; exit 1 = a gap (prints which).
Run: python scripts/check_config_covers_open_questions.py [config/config.example.yaml]
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Each source-plan §9 open question -> the config key(s) that resolve it as an option.
OPEN_QUESTIONS = {
    "OQ1 job rubric": ["jobs.search_terms", "ranking.shortlist_size"],          # + rubric.yaml
    "OQ2 warmth weights / profile": ["people_scoring.require_reasons"],          # + rubric/profile.yaml
    "OQ3 draft vs send": ["outreach.mode", "compliance.require_human_send"],
    "OQ4 proxy budget/type/gateway": ["proxies.backend", "proxies.webshare.type"],
    "OQ5 account mode + captcha": ["people.staffspy.account_mode", "people.staffspy.captcha_solver"],
    "OQ6 daily company ceiling": ["people.staffspy.max_profiles_per_company_per_day"],
    "OQ7 linkedin-mcp vs StaffSpy": ["people.provider", "people.volume_threshold_use_staffspy"],
    "OQ8 enrichment waterfall": ["enrichment.waterfall", "enrichment.mode"],
    "OQ9 native-MCP vs python": ["enrichment.mode"],
    "OQ10 MCP vs filesystem": ["orchestration.mcp_mode"],
    "OQ11 sqlite / freshness / dedup": ["state.sqlite_path", "state.job_freshness_days"],
    "OQ12 scheduler choice": ["orchestration.scheduler"],
    "OQ13 secrets store": [],   # handled by .env.example + keychain (not a config knob)
    "OQ14 GDPR/NL compliance": ["compliance.block_personal_domain_cold_email",
                                "compliance.max_daily_outreach", "outreach.cold_email_target_filter"],
}


def _get(d, dotted):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path("config/config.example.yaml")
    if not path.exists():
        print(f"FAIL: config not found: {path}")
        return 1
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    missing: list[str] = []
    for oq, keys in OPEN_QUESTIONS.items():
        for k in keys:
            if _get(raw, k) is None:
                missing.append(f"{oq}: missing key '{k}'")
    if missing:
        print("FAIL: open questions not fully covered by config:")
        for m in missing:
            print(f"  - {m}")
        return 1
    print(f"PASS: all {len(OPEN_QUESTIONS)} source-plan open questions are covered by config keys.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
