# Evaluation Results — linkedin-coffee-pipeline D6

Run at: `2026-06-27T18:18:39Z`  |  Python: `3.12.12`

**Overall: ALL PASS**

## Per-Capability Scorer Table

| Capability | Scorer | Pass Bar | Result | Exit | Duration |
|---|---|---|---|---|---|
| config-covers-open-questions | `check_config_covers_open_questions.py` | exit 0 | **PASS** | 0 | 0.06s |
| eval-plan-exists | `gate_eval_plan_exists.py docs/GOAL.md` | exit 0 | **PASS** | 0 | 0.06s |
| ledger-exists | `gate_ledger_exists.py docs/LEDGER.md` | exit 0 | **PASS** | 0 | 0.06s |
| contracts-valid | `pytest test_contracts` | 100% | **PASS** | 0 | 0.42s |
| config-options+baselines | `pytest test_config` | 100% | **PASS** | 0 | 0.58s |
| state-dedup | `pytest test_state` | 100% | **PASS** | 0 | 0.32s |
| rank-deterministic | `pytest test_rank_jobs` | 100% | **PASS** | 0 | 1.43s |
| warmth-cites-reasons | `pytest test_score_people` | 100% | **PASS** | 0 | 1.26s |
| enrich-waterfall | `pytest test_enrich` | 100% | **PASS** | 0 | 1.18s |
| mcp-gating | `pytest test_mcp` | 100% | **PASS** | 0 | 1.22s |
| outreach-draft-only | `pytest test_outreach` | 100% | **PASS** | 0 | 0.33s |
| claude-desktop-merge | `pytest test_claude_desktop_config` | 100% | **PASS** | 0 | 0.25s |
| e2e-smoke | `pytest test_e2e_smoke` | 100% | **PASS** | 0 | 1.41s |
| installer-idempotent | `scripts/test_install_dryrun.sh` | exit 0 | **PASS** | 0 | 0.35s |

## Pipeline Funnel (fresh golden e2e run)

| Stage | Count | Bar |
|---|---|---|
| jobs_fetched | 5 | `████████████████████` |
| shortlisted | 4 | `████████████████░░░░` |
| companies | 1 | `████░░░░░░░░░░░░░░░░` |
| people | 3 | `████████████░░░░░░░░` |
| people_to_meet | 2 | `████████░░░░░░░░░░░░` |
| drafts | 1 | `████░░░░░░░░░░░░░░░░` |

## Notes

- Funnel run uses **golden synthetic data** (`eval/golden/`) in a tmpdir.
  No real LinkedIn scraping or personal data is used.
- `installer-idempotent` runs `./install.sh --dry-run` + `wire_claude_desktop.py --print`.
- `outreach-quality (LLM judge)` rubric is in `eval/outreach_rubric.md`;  that scorer requires a running LLM and is not automated here.
