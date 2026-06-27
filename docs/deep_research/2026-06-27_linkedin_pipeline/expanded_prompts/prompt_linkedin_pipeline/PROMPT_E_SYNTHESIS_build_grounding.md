# PROMPT E — SYNTHESIS: a build-grounding dossier + architecture for the LinkedIn Coffee Pipeline

You are now the **Synthesis Agent & lead architect**. **You have been given four detailed research reports** from prior deep-research rounds:

- **Report A — Repo landscape & architecture:** current state/maintenance/capabilities/gotchas of JobSpy, StaffSpy, linkedin_scraper, linkedin-mcp-server, proxy orchestration tools, enrichment APIs, and MCP server frameworks; plus a proposed reference architecture and data contracts.
- **Report B — Claude/MCP ecosystem:** which LinkedIn/enrichment capabilities already exist as Claude-native connectors / MCP servers / agent skills, their maturity and Claude-Desktop usability, and reuse-vs-build verdicts.
- **Report C — Engineering best-practices:** concrete, cited best-practices for scraping resilience & account safety, proxy rotation/health, SQLite state/dedup, enrichment-waterfall design, MCP security + human-in-the-loop gating, local scheduling, and secrets.
- **Report D — GDPR/Dutch-law legality:** the lawful-basis analysis for enriching contact data and for sending cold 1:1 coffee-chat outreach (email + LinkedIn DM) as an individual in NL/EU, with a defaults-level do/don't checklist.

Your job is to **synthesize, not repeat** — cross-reference the four reports, resolve contradictions, identify gaps, and produce a single, concrete, build-ready dossier for the repo at `linkedin-coffee-pipeline`.

> **CENTRAL SYNTHESIS QUESTION:** Given everything the four reports establish, what is the **correct, safe, maintainable architecture and configuration** for this local LinkedIn networking pipeline — and what should each component, default, and document actually be?

## APPENDIX: PROJECT CONTEXT AND REFERENCE MATERIALS

The repo is a **separate, easily-shared, installable** product (easy installer for a non-technical user; one-command Claude Desktop MCP wiring). Its design split:
- **Deterministic Python core** (cron/launchd): `proxy_check.py` → `fetch_jobs.py` (JobSpy, proxied) → `rank_jobs.py` (rubric pre-filter); and `fetch_staff.py` (StaffSpy, own IP) → `score_people.py` (warmth) → `enrich.py` (waterfall).
- **Claude Desktop MCP layer**: a custom pipeline MCP (`get_shortlist`, `run_jobspy`, `run_staffspy` [gated], `score_people`, `enrich_person` [gated], `draft_outreach`, `mark_contacted`) + reused enrichment MCPs (Apollo/Prospeo/Kaspr/Hunter) + the `linkedin-mcp-server` for reads/drafts.
- **State**: SQLite (`seen_jobs`, `companies_enumerated`, `people_contacted`).
- **North star**: a ranked, warm list of people worth a coffee, with cited reasons (shared school/employer, role fit), and a personalized non-salesy ask. **Draft-only baseline; human sends.**
- **All source-plan open questions are resolved as config options with baselines** (not hardcoded), in `config/config.example.yaml`.

## DELIVERABLES (be concrete and specific)

### Deliverable 1 — Reference architecture
A single labeled architecture (mermaid `flowchart TB`, tagged `<!--FIG:final_architecture|The synthesized end-to-end architecture: deterministic core, state, MCP layer, human gates-->`) + prose walking it top-to-bottom: every module, the data contract on each edge, where the deterministic↔LLM boundary sits, and where the human gates are.

### Deliverable 2 — The resolved configuration (the heart of this synthesis)
A complete, annotated `config.yaml` proposal that picks **baselines** and lists **alternatives** for every open question: proxy backend + provider + budget; job rubric shape; warmth-weight defaults; people-layer choice (linkedin-mcp vs StaffSpy vs both) with the volume threshold; enrichment waterfall order; account-safety caps (per-day/per-company/delays); outreach mode (draft-only) + send sequence; scheduling mode. Justify each baseline by citing which report supports it. Resolve any contradictions between reports A/B/C explicitly.

### Deliverable 3 — Component build-vs-reuse decisions + a prioritized build roadmap
A table: component → reuse/wrap/build + reason. Then a **P1/P2/P3 prioritized roadmap** mapping to the repo's deliverables D1–D6 (scaffold/config/contracts/state; jobs core; people+enrichment; MCP server; installer/docs/scheduling; tests/eval/gates), with go/no-go checkpoints and fallbacks ("if StaffSpy selectors are broken → fall back to linkedin-mcp-server for the people layer").

### Deliverable 4 — The compliance & account-safety operating envelope
Synthesize Reports C + D into the concrete defaults the software must enforce: target filters (corporate-domain-only cold email), daily caps, delays, retention windows, opt-out text, the LIA template, and the **hard red lines to block in code**. This becomes `docs/COMPLIANCE.md`. Include the legality decision-tree (tagged `<!--FIG:compliance_decision|When may I enrich + send, by channel and contact type-->`).

### Deliverable 5 — Risks, gaps, and open questions
What the four reports left unresolved or contradicted; the top risks (selector rot, account ban, ToS/legal, proxy economics) with mitigations; and what to re-verify before go-live.

## Output specification
Target **8,000–12,000 words**. Heavy use of tables (config, build-vs-reuse, roadmap, safety caps). Inline citations carried forward from Reports A–D + a consolidated `## References`. At least the three tagged mermaid diagrams named above, each legible/top-to-bottom.

## CRITICAL REMINDERS FOR SYNTHESIS
- **Synthesize, don't summarize** — cross-reference and resolve, don't restate each report in turn.
- Every config baseline must be **traceable to a report** and have a stated alternative.
- Keep **draft-only + human-send** and **confirmation-gating on account/credit actions** as non-negotiable defaults.
- Keep the **JobSpy-proxied-public** vs **own-IP-authenticated** proxy postures distinct.
- Make the **corporate-vs-personal-address** legal axis operational in the config.
- Calibrate for a **single low-volume individual in Amsterdam**, not an enterprise.
- Carry citations forward faithfully; never fabricate; preserve verification flags.
