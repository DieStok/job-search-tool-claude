# ☕ linkedin-coffee-pipeline

**Turn job-board noise into a short, warm list of people worth grabbing coffee with —
attached to roles you'd actually want.**

> Networking is king. The job board is just the lens.
> **Jobs → companies → people → a contact path → a genuine, non-salesy coffee ask.**

This is a **local** tool. A deterministic Python core does the heavy lifting (scraping,
de-duping, ranking, warmth-scoring) on a schedule. **Claude Desktop** adds the judgment
layer — *who* to meet, *why*, and a personalized draft — by talking to this pipeline
through a small MCP server. **Claude drafts; you send.** Nothing is sent automatically.

---

## Install (no GitHub knowledge needed)

1. Download/clone this folder onto your Mac.
2. Open Terminal, drag the folder in (or `cd` into it), and run:

   ```bash
   ./install.sh
   ```

   That installs everything (it even installs `uv` for you if needed), creates your
   config files from sensible baselines, and prints your next steps.

3. Wire it into Claude Desktop:

   ```bash
   ./install.sh claude-desktop
   ```

   Then restart Claude Desktop. (See [docs/CLAUDE_DESKTOP.md](docs/CLAUDE_DESKTOP.md).)

> Prefer to do it by hand? `./install.sh --dry-run` prints every command without running it.

---

## Set it up (3 files)

The installer copies these from `*.example.yaml`. Edit them:

| File | What it's for |
|---|---|
| `config/profile.yaml` | **Who you are** — schools, employers, skills. This is what makes matches *warm*. |
| `config/rubric.yaml` | **Which jobs you want** + how much each warmth signal (shared school, etc.) counts. |
| `config/config.yaml` | All the knobs (proxy, people layer, enrichment, scheduling). **Baselines are already chosen** — every open design question is a documented option here. |

Secrets (any API keys) go in `.env` — never in the config, never in git.

---

## Use it

**The deterministic core** (runs without Claude, e.g. each morning on a schedule):

```bash
.venv/bin/lcp jobs fetch     # pull fresh jobs (JobSpy) and de-dup
.venv/bin/lcp jobs rank      # rank them into a shortlist using your rubric
.venv/bin/lcp doctor         # health check + a funnel of what happened
```

**The judgment + networking layer** (in Claude Desktop, once wired):
Ask Claude things like *"Show me my shortlist, pick 3 companies worth a deep look, find
people there I share background with, and draft a coffee-chat message to the warmest one."*
Claude uses the pipeline's MCP tools. Anything risky (enumerating a company, spending an
enrichment credit, sending) is **confirmation-gated**.

---

## How it works

```
DETERMINISTIC CORE (plain Python, schedulable)        JUDGMENT LAYER (Claude Desktop)
  proxy check → fetch jobs → rank → shortlist.json  ─┐
  fetch staff (your own IP) → warmth score ──────────┼─►  reads files + MCP tools
       → people_to_meet.json                         │    • picks roles & companies
  enrich (free-tier waterfall) → contacts            │    • ranks people to meet (+ why)
                                                      │    • drafts the coffee ask (you send)
        state.sqlite  (no re-scrape, no double-ask) ──┘
```

- **Jobs** use JobSpy (LinkedIn/Indeed/Glassdoor/Google), proxied for scale.
- **People** use your **own logged-in LinkedIn** (via `linkedin-mcp-server` for low volume,
  or StaffSpy for batch) — **never through a proxy**, human-paced for account safety.
- **Enrichment** cascades across free-tier providers (Apollo/Prospeo/Kaspr/Hunter) and
  prefers EU-friendly sources.

## Please read before reaching out

[docs/COMPLIANCE.md](docs/COMPLIANCE.md) — GDPR / Dutch-law guidance for 1:1 networking
(corporate-vs-personal addresses, LinkedIn-DM-first, the human-send rule). Engineering
note, not legal advice. The tool enforces the hard red lines in code.

## More docs
- [docs/CLAUDE_DESKTOP.md](docs/CLAUDE_DESKTOP.md) — MCP wiring + which enrichment MCPs to add
- [docs/GOAL.md](docs/GOAL.md) — the full build spec (deliverables, acceptance criteria)
- [docs/research/](docs/research/) — the grounding research the baselines are built on

## License
MIT.
