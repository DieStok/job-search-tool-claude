# CLAUDE.md — guide for Claude (Code & Desktop)

This repo is **linkedin-coffee-pipeline**: a local tool that turns job-board noise into a
ranked, warm list of people worth a coffee chat, attached to roles the operator would want.
**Jobs → companies → people → a contact path → a genuine, non-salesy coffee ask.**

## Your role when driving this tool
- **Deterministic Python does the heavy lifting** (scrape, dedup, rank, warmth-score). Prefer the
  `lcp` CLI / the MCP tools over re-implementing logic in conversation.
- **You do the judgment + relationship layer:** pick roles & companies worth a deeper look, decide
  *who* is worth meeting and *why*, and draft the outreach. **You draft; the human sends.**
- **Confirmation-gated actions:** `run_staffspy` (account risk) and `enrich_person` (credit spend)
  must be called with `confirm=true` only after the human agrees. Never auto-send outreach.
- **Read `docs/COMPLIANCE.md` before any outreach** (GDPR / NL ePrivacy). The code enforces the
  red lines (no cold email to personal domains; human-send required), but you should respect them too.

## MCP tools (server: `linkedin-coffee-pipeline`)
`get_shortlist`, `list_people_to_meet`, `run_jobspy`, `score_people` (un-gated reads/triggers) ·
`run_staffspy(company, confirm)`, `enrich_person(profile_url, confirm)` (**gated**) ·
`draft_outreach(profile_url)` (never sends) · `mark_contacted(profile_url, status)`.

## Deterministic CLI (run these rather than reimplementing)
```
lcp jobs fetch      # JobSpy + enabled supplemental sources, dedup
lcp jobs rank       # rubric scoring -> shortlist.json
lcp people score    # warmth scoring -> people_to_meet.json (cited reasons)
lcp enrich person <url>   # free-tier contact waterfall
lcp doctor          # config + state + last-run funnel
lcp mcp --selfcheck # list MCP tools + which are gated
```

## Config (everything is a knob)
`config/config.yaml` (copy of `config.example.yaml`) — every design decision is a documented option
with an allowed-values comment. `config/profile.yaml` = who the operator is (warmth matching).
`config/rubric.yaml` = which jobs + warmth weights. **Secrets live in `.env` / the OS keychain, never
in config and never committed.**

## Setup
- **Claude Code:** the project ships `.mcp.json`; Claude Code auto-detects it — approve the
  `linkedin-coffee-pipeline` server when prompted. Run `./install.sh` first to create `.venv`.
- **Claude Desktop:** `./install.sh claude-desktop` merges the server into `claude_desktop_config.json`.
- See `README.md` and `docs/CLAUDE_DESKTOP.md`.

## Conventions
- Don't put secrets, PII, or absolute local paths into committed files.
- Keep tool responses small (avoid context bloat); for big batches use the CLI, not many MCP round-trips.
