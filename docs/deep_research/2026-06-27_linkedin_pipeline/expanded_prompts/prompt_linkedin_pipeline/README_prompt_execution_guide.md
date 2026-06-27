# Deep Research Execution Guide — LinkedIn Coffee Pipeline grounding

Five prompts: **4 parallel domain sub-prompts (A–D) + 1 synthesis (E)**. Built for
claude.ai web Research. The A–D runs are independent and **run in parallel** (submit all
up front; Research continues server-side); E runs **after** A–D, with the four reports
attached.

| Prompt | Focus | Depends on | Est. Research time | Key output |
|---|---|---|---|---|
| **A** | OSS repo landscape + reference architecture (JobSpy, StaffSpy, linkedin-mcp, proxies, MCP frameworks) | — | 20–40 min | Component audit, build-vs-reuse, architecture + contracts |
| **B** | Claude/MCP/agent-skill ecosystem for LinkedIn + enrichment; reuse-vs-build | — | 20–40 min | Provider/MCP master table, Claude Desktop wiring, reuse verdicts |
| **C** | Per-component engineering best-practices (resilience, proxy, state, waterfall, MCP security, scheduling, secrets) | — | 20–40 min | Cited best-practice requirements per component |
| **D** | GDPR / Dutch-law legality of cold 1:1 outreach + enrichment as an individual (LOAD-BEARING) | — | 20–40 min | Lawful-basis analysis + do/don't + LIA template + decision tree |
| **E** | SYNTHESIS → build-ready dossier: architecture, resolved config, roadmap, COMPLIANCE | A, B, C, D | 25–45 min | The dossier that grounds the repo's plans + docs |

## Execution
1. Submit **A, B, C, D** each into its own claude.ai project chat with **Research mode ON**. Let them run concurrently (server-side).
2. As each finishes, capture its report markdown to `final_outputs/prompt_linkedin_pipeline/sub_reports/{A,B,C,D}.md`.
3. Run **E** with A–D attached → capture; synthesize locally into `final_outputs/prompt_linkedin_pipeline/full_report.md` (citations + `## References` + tagged mermaid).
4. Render diagrams, run the agent-review-panel + reference audit → `review/`, build the PDF, package.

## How outputs feed the build
- **A + C** → the per-deliverable plans (`docs/plans/`) and `src/lcp/*` design.
- **B** → `docs/CLAUDE_DESKTOP.md` + the MCP server (D4) reuse-vs-build decisions.
- **D** → `docs/COMPLIANCE.md` + the software red-lines (target filters, caps, opt-out).
- **E** → the consolidated dossier cross-checking `config/config.example.yaml` baselines.

## Design decisions
- **Split, not monolith:** 4 distinct domains (OSS/architecture, ecosystem, best-practices, law) → depth over breadth; D especially needs a dedicated run (it's the hardest, load-bearing unknown).
- **Parallel, server-side:** never serial-wait; submit all, poll-and-capture.
- A fast tactical pass (the `research-analyst` subagent, `docs/research/2026-06-27_volatile_facts_grounding.md`) already resolved the *volatile* facts (free tiers, MCP availability, pacing); these deep runs add the *depth* (design patterns, architecture, legal reasoning) the build plans cite.
