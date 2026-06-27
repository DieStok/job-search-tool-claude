# CENTRAL LEDGER — LinkedIn Coffee Pipeline (2026-06-27 →)

> **Live work log.** The plan/spec is `docs/GOAL.md`.
> Records WHAT IS DONE, WHAT IS IN FLIGHT, WHO IS DOING IT, and DECISIONS.
> Updated every loop wake. Newest status block on top. DoD = §9 of the goal doc.
> **Branch:** `main` (fresh repo at `/Users/dstoker6/automation/linkedin-coffee-pipeline`).
> **Routing decision:** tier = **large** · behavior-change? **mostly no** (deterministic
> data tooling; only the MCP tool-surface is agent-behavior → standard) · greenfield
> multi-deliverable product, full ceremony on core, code-graded gates everywhere.
> **Loop bounds:** `--max-runs=12` · `max_consecutive_failures=3` · `max_runtime_min=600`
> · cost ceiling: keep Opus for orchestration/review; implementation on Sonnet subagents.

## Workstream status at a glance

| ID | Deliverable | State | Owner | Blocking |
|---|---|---|---|---|
| D1 | Scaffold/config/contracts/state | ✅ DONE (14 tests) | Opus orchestrator | — |
| D2 | Jobs core | ✅ DONE (46 tests total) | sonnet python-pro | — |
| D3 | People + enrichment | RUNNING | sonnet python-pro | needs D1 (have it) |
| D4 | MCP server | NOT STARTED | (sonnet subagent) | needs D2✅+D3 |
| D5 | Installer/docs/sched | PARTIAL (COMPLIANCE.md done) | Opus + (sonnet) | needs D4 for wiring |
| D6 | Tests/eval/gates | NOT STARTED | woven | cross-cuts |
| E2 | deep-research-Claude-web hardening (5 improvements) | RUNNING | sonnet general | agent_fleet repo |

## Long-running tasks in flight

| Job/ref | What | state | notes |
|---|---|---|---|
| `research-analyst a095…` | Volatile §10 facts (free tiers, MCP, GDPR, StaffSpy/JobSpy state, proxy, pacing, outreach) | RUNNING | feeds config baselines + COMPLIANCE.md |
| `deep-research-Claude-web` | Repos / design patterns / LinkedIn agent-skill ecosystem / per-component best-practices / GDPR-NL deep-dive | QUEUED | operator-requested; feeds plans/docs |

---

## Pre-loop preconditions

- [x] Goal doc authored (`docs/GOAL.md`) with AC-NNN + Evaluation Plan
- [x] Ledger created (this file)
- [x] Gate scripts vendored into `scripts/gates/`
- [x] Routing recorded (large; deterministic core + standard MCP surface)
- [x] Loop bound + circuit breakers set (above)
- [ ] Eval golden seed set authored (`eval/golden/`) — part of D6

## Decisions log

- **2026-06-27 D-1:** Pi unavailable (no `.env` key; OneCLI broker returns connection
  error for LLM calls). Fell back to **Sonnet subagents** (documented default implementer
  since 2026-06-15). Operator can re-point to Pi by restoring broker/.env.
- **2026-06-27 D-2:** All source-plan open questions resolved as **config options +
  baselines** (operator instruction), not hardcoded. See GOAL §10.
- **2026-06-27 D-3:** Repo is **separate & self-contained** at
  `/Users/dstoker6/automation/linkedin-coffee-pipeline`; not nested in agent_fleet.
- **2026-06-27 D-4:** Baseline outreach mode = **draft_only** (send opt-in + gated).
- **2026-06-27 D-5:** Operator added a `/deep-research-Claude-web` pass (repos, design
  patterns, ecosystem, per-component best-practices, GDPR/NL). Launched as research input.

## Wake log

### Wake 0 — 2026-06-27 (Opus orchestrator)
- **Advanced:** read source plan; ran set-work-loops; scaffolded separate repo;
  authored GOAL.md (6 deliverables, AC-NNN, Evaluation Plan); created this ledger;
  launched volatile-facts research subagent; vendored gates.
- **Next:** finish D1; launch deep-research-Claude-web; fan out D2/D3.
- **Blocked:** none.

### Wake 1 — 2026-06-27 (Opus orchestrator)
- **Advanced:** volatile-facts research landed → `docs/research/2026-06-27_volatile_facts_grounding.md`
  (config baselines). Crafted deep-research-Claude-web prompt set (A–D + synthesis + README).
  Built + committed D1 (14 tests). Launched E2 skill-hardening subagent (agent_fleet).
  Built + committed D2 (jobs core, 46 tests total). Wrote COMPLIANCE.md (GDPR/NL).
  Operator added: (a) E2 5-improvement skill hardening; (b) live test with their logged-in
  Firefox — do a real "deep learning bioinformatics / AI for Biology" search + example result
  ONCE the core lands (task #13).
- **In flight:** D3 (people+enrichment) sonnet; E2 (skill hardening) sonnet; deep-research
  prompts crafted but NOT yet submitted (will dogfood AFTER E2 lands → real e2e test of the
  upload-dedup + login-check fixes).
- **Next:** on D3 land → review+commit, launch D4 (MCP). On E2 land → review+merge, then
  submit deep research. Then D5 installer + D6 tests/gates. Then live demo (#13).
- **Blocked:** deep-research submission intentionally held until E2 hardening merges.
- **Usage:** 5h 3% (green), 7d 80%; implementation on Sonnet to protect weekly Opus.
