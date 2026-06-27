# Wiring linkedin-coffee-pipeline into Claude Desktop

The pipeline ships a small **MCP server** so Claude Desktop can drive it as first-class
tools. This is the "judgment + networking" layer: Claude reads your shortlist and people,
picks who's worth a coffee and why, and drafts the ask. Risky actions are confirmation-gated.

## 1. Wire the pipeline MCP server (one command)

```bash
./install.sh claude-desktop
```

This merges an entry into your `claude_desktop_config.json` (it **backs up first** and
**preserves your other MCP servers**), then asks you to restart Claude Desktop. To see the
exact JSON without changing anything:

```bash
.venv/bin/python scripts/wire_claude_desktop.py --repo "$(pwd)" --print
```

The entry runs `python -m lcp.mcp_server` from this repo's `.venv`. Tools exposed:

| Tool | Gated? | What it does |
|---|---|---|
| `get_shortlist` | no | read the ranked job shortlist |
| `list_people_to_meet` | no | read the warmth-ranked people |
| `run_jobspy` | no | trigger a fresh job fetch + rank |
| `run_staffspy` | **yes** | enumerate staff at a company (account risk) |
| `score_people` | no | (re)compute warmth from staff + your profile |
| `enrich_person` | **yes** | spend an enrichment lookup for a contact path |
| `draft_outreach` | no | draft a coffee-chat message (never sends) |
| `mark_contacted` | no | record that you reached out (dedup) |

> Filesystem-only alternative: set `orchestration.mcp_mode: filesystem_only` and instead add
> the official **Filesystem MCP** pointed at this repo's `data/` folder. The custom server is
> recommended (Claude can *trigger* runs, and gating is built in).

## 2. The people layer — your own LinkedIn session

For reading actual LinkedIn profiles/companies, add **`stickerdaniel/linkedin-mcp-server`**
(actively maintained; v4.16.1 as of 2026-06). It authenticates with **your own logged-in
browser session** and covers low-volume people lookups — often enough to skip StaffSpy.

- It imports cookies from **Chrome/Brave/Edge/Safari**. **Firefox is not auto-imported** —
  if your LinkedIn login is in Firefox, pass the `li_at` cookie explicitly (the server accepts
  a `LINKEDIN_COOKIE`/`li_at` value) or log in once via its browser flow.
- Keep it low-volume and human-paced (≤50 profiles/day, 30–60s apart). See
  [COMPLIANCE.md](COMPLIANCE.md) for the account-safety envelope.

## 3. Enrichment MCPs (optional — "a way to reach this person")

Add 2–3 at most (too many MCPs bloat the context and degrade output). From the research,
these work on Claude Desktop **free/Pro** today:

| Provider | How to add | Free tier | Notes |
|---|---|---|---|
| **Apollo** | Settings → Connectors → Add URL `https://mcp.apollo.io/mcp` (OAuth) | yes | **Set credit tools to "Approval required"** (gating). Email + phone. |
| **Prospeo** | custom connector `https://mcp.prospeo.io` (API key) | 75/mo | LinkedIn-URL → email. |
| **Kaspr** | per Kaspr's MCP docs | 15 email + 5 phone/mo | EU/French (GDPR-friendlier). Phone. |
| **Hunter** | API-key MCP (remote endpoint) | 50/mo | Email only; verification strength. |

Prefer **Kaspr/Dropcontact** as the *data source* for NL outreach (EU posture). Always keep
Apollo's confirmation gate on so credits aren't spent silently.

## 4. Try it

After restarting Claude Desktop, ask:

> "Use linkedin-coffee-pipeline: show my shortlist, pick 3 companies, find people there I
> share a school or past employer with, and draft a 20-minute coffee-chat message to the
> warmest one. Don't send anything."
