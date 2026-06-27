# PROMPT B — The LinkedIn × Claude / agent-skill / MCP ecosystem: reuse vs build

You are a **senior MCP / agent-integration engineer** specializing in:
1. The Claude Desktop connector & MCP ecosystem (native connectors, Desktop Extensions/`.mcpb`, stdio servers, OAuth connectors).
2. Sales-intelligence & contact-enrichment APIs and their MCP/connector offerings (Apollo, Hunter, LeadMagic, Prospeo, Derrick, Unipile).
3. The practical maturity assessment of community MCP servers and "agent skills" for recruiting/networking automation.

You are grounding a **local, single-user** LinkedIn networking pipeline for an Amsterdam job-seeker. A deterministic Python core scrapes jobs (JobSpy) and, on selected companies, staff (StaffSpy, own logged-in IP). **Claude Desktop** is the judgment layer: it reads the Python outputs, ranks *people worth meeting*, enriches a contact path, and drafts coffee-chat outreach — ideally calling enrichment + LinkedIn-read capabilities **as MCP tools in-conversation**, with confirmation gates on anything that spends credits or touches the account.

> **CENTRAL RESEARCH QUESTION:** What LinkedIn / contact-enrichment / networking capabilities already exist *today* as Claude-native connectors, MCP servers, or agent skills — how mature and how usable are they on **Claude Desktop (free/Pro)** specifically — and for each pipeline need (enrich-a-contact, read-a-profile, trigger-a-scrape), should we **reuse an existing MCP** or **build our own thin server**?

Decompose into:
1. The contact-enrichment MCP/connector landscape (the "give me a way to reach this person" layer).
2. The LinkedIn-read / account-action MCP landscape (deep-dive a profile/company; optionally connect/message).
3. Claude Desktop integration mechanics + the reuse-vs-build decision + the context-bloat constraint.

## Part 1 — Enrichment MCP/connector landscape
For **each** provider — **Apollo.io, Hunter.io, LeadMagic, Prospeo, Derrick, Findymail, ContactOut, RocketReach, Dropcontact, Kaspr** — report **(a)** whether it has a **native Claude connector / official MCP** vs a Composio-routed MCP vs none, **(b)** whether the MCP works on the **free/Pro** tier of Claude Desktop, **(c)** what the tools do (LinkedIn-URL→email, name+company→email, phone, verify), **(d)** any **confirmation-gating** before credit-consuming actions (Apollo's official plugin reportedly warns + requires confirmation — verify), **(e)** setup friction (OAuth vs API key, Desktop config).
**Search for:** "Apollo MCP Claude connector confirmation gate 2026", "LeadMagic MCP Claude Desktop", "Prospeo MCP native or composio", "Hunter MCP composio", "Derrick MCP", "Claude Desktop connectors directory enrichment".

## Part 2 — LinkedIn-read / account-action landscape
- **linkedin-mcp-server** (`stickerdaniel/...`): tools, auth (own browser session/cookie), what it reads (profile incl. education + contact_info, company, jobs, job detail), maintenance, star count, account-risk caveats. **Can it alone cover a LOW volume of people lookups and let us skip StaffSpy?** Give a clear verdict.
- **Unipile** (hosted LinkedIn API; backs linkedin-mcp-server): managed alternative; read + message; any MCP.
- **Linked API** (`linkedapi.io`): cloud-browser account driver; read + connect/message.
- Any other LinkedIn MCP servers / "agent skills" on GitHub, Smithery, the Claude connector directory, mcp.so, awesome-mcp lists.
**Search for:** "linkedin MCP server github 2026", "Unipile MCP", "smithery linkedin mcp", "claude agent skill linkedin networking".

## Part 3 — Claude Desktop integration + reuse-vs-build + context bloat
- How a local MCP server is installed into Claude Desktop in 2026: `claude_desktop_config.json` `mcpServers` stdio entries; **Desktop Extensions / `.mcpb` bundles** (one-click install) — which is the friendliest for a **non-technical** user, and how to generate it.
- The **"don't wire too many MCPs"** problem: verbose tool responses fill the context window and degrade output. Recommend a concrete cap (how many enrichment MCPs at once) and when to switch to SDK/CLI batch instead.
- A **reuse-vs-build table**: pipeline need → existing MCP to reuse (which) OR build-our-own thin tool (why). Specifically: should our custom "pipeline MCP" (exposing `run_jobspy`, `run_staffspy`, `get_shortlist`, `mark_contacted`) coexist with reused enrichment MCPs, or wrap everything?

## Output specification
Target **5,000–8,000 words**. A master table: provider/tool → native-MCP? → free-tier-usable? → LinkedIn→email? → phone? → confirmation-gated? → reuse/build verdict. Inline citations + `## References`. One mermaid diagram tagged `<!--FIG:mcp_topology|How Claude Desktop wires the custom pipeline MCP alongside reused enrichment + LinkedIn-read MCPs-->`.

## Critical reminders
- Be explicit about **Claude Desktop free vs Pro** usability — many MCPs assume paid API keys even if the connector is "native".
- Verify, don't assume, native-vs-Composio status — sources conflict (esp. Prospeo).
- Give a crisp **reuse-vs-build verdict per need**, not just a catalogue.
- Note Apollo's LinkedIn-company-page removal (2025) and Proxycurl's death as ToS-climate signals.
