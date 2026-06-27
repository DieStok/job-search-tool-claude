# PROMPT A — Open-source repo & design-pattern landscape for a local LinkedIn job+networking pipeline

You are a **senior data-engineering & web-automation architect** with deep expertise in:
1. Web scraping at scale (anti-bot evasion, proxy orchestration, rate-limit survival) against hostile targets like LinkedIn.
2. ETL/pipeline architecture — the split between deterministic batch cores and LLM/agent judgment layers, with durable state and dedup.
3. The Model Context Protocol (MCP) and its Python server ecosystem (FastMCP, the official `modelcontextprotocol/python-sdk`).
4. The practical maintenance reality of community scraping repos (selector rot, ToS-driven takedowns, fork drift).

You are grounding the build of a **local, single-user tool** for an Amsterdam-based job-seeker. The product turns job-board noise into a **ranked, warm list of people worth grabbing coffee with**, attached to roles they'd genuinely want. Flow: pull lots of fresh jobs+companies (deterministic, proxied) → narrow to roles they'd like (cheap pre-filter + Claude judgment) → for those companies pull the *people* and their education/background (the user's own logged-in LinkedIn, only on selected companies) → enrich a contact path → Claude ranks who to meet + drafts a genuine coffee-chat ask → human approves/sends. The split is: **deterministic Python does scraping/dedup/ranking; Claude Desktop (via MCP) does the relationship judgment.**

> **CENTRAL RESEARCH QUESTION:** For each open-source component this pipeline could use, what is its *current* (mid-2026) state, maintenance health, capability surface, and known failure modes — and what is the **correct architecture** for assembling them into a robust, debuggable, cron-able local pipeline with a clean deterministic-core / LLM-layer split?

Decompose into:
1. Component-by-component capability + maintenance audit.
2. The "build vs reuse" call per component.
3. The reference architecture (data contracts, state, scheduling, the deterministic↔LLM boundary).
4. Concrete gotchas that will bite a builder in 2026.

## Part 1 — Component audit (do not skip any)

For **each** repo/tool below, report: **(a)** what it produces (exact data fields / API surface), **(b)** current maintenance status (last commit, open-issue themes, stars, whether selectors/endpoints still work in 2026), **(c)** known strengths & failure modes, **(d)** how to run it today (install, auth model, key params — e.g. JobSpy's `proxies=`, StaffSpy's session/captcha handling), **(e)** ToS/legal exposure & takedown risk.

- **JobSpy** — `speedyapply/JobSpy`. Multi-board job scraper (LinkedIn/Indeed/Glassdoor/Google/ZipRecruiter). Confirm current supported boards, NL/EU coverage for Indeed+Glassdoor, native proxy rotation, rate-limit behavior (~per-IP page cap).
- **StaffSpy** — `cullenwatson/StaffSpy`. Company staff scraper (education, experiences, skills, connection contact info). Confirm own-IP/logged-in requirement, captcha/session_file behavior, per-search ~1000 cap, realistic per-day limits before account flags.
- **linkedin_scraper** — `joeyism/linkedin_scraper`. Playwright Person/Company/Job. Pydantic. Single-lib alternative.
- **linkedin-api (unofficial)** — `tomquirk/linkedin-api`. Voyager endpoints; cookie-auth; ToS-violating; intermittent repo access.
- **linkedin-mcp-server** — `stickerdaniel/linkedin-mcp-server`. Reads LinkedIn via the user's own browser session as MCP tools.
- **Proxy orchestration** — `scrapoxy/scrapoxy`, `jhao104/proxy_pool`, `constverum/ProxyBroker`, `mitmproxy/mitmproxy`, the `rotating-proxy` PyPI pkg. Role of each as a single rotating gateway for JobSpy.
- **Enrichment** — Apollo.io, Prospeo, Hunter.io, LeadMagic, Findymail, ContactOut, RocketReach, Dropcontact, Kaspr, Derrick; plus Coresignal, People Data Labs, Bright Data, Unipile, Linked API. (Capability + API shape only here; legal/free-tier depth is Prompt D / a separate tactical pass.)
- **MCP server frameworks** — `FastMCP` (v2) vs the official `modelcontextprotocol/python-sdk`. Confirm which is the right base for a local stdio MCP server in 2026, how confirmation/elicitation + human-in-the-loop gating is expressed, and packaging for Claude Desktop.

**Search for:** "JobSpy 2026 Indeed Glassdoor blocked", "StaffSpy captcha 2026 issues", "linkedin-mcp-server release", "FastMCP vs official python MCP SDK 2026", "MCP elicitation human confirmation tool", "Scrapoxy vs proxy_pool single gateway".

> ⚠️ **Proxycurl is DEAD** (shut down July 2025 after a LinkedIn lawsuit + permanent injunction). Do NOT design around it. Its successor NinjaPear does not scrape LinkedIn. Note this explicitly.

## Part 2 — Build vs reuse, per component
A table: component → reuse-as-is / wrap-with-adapter / build-our-own, with the reason (maintenance risk, fit, license). License check each (MIT/AGPL/etc.) — AGPL (e.g. Scrapoxy) has distribution implications even for a local tool that may be shared.

## Part 3 — Reference architecture for assembly
Describe the **canonical** way to wire this:
- The **deterministic core ↔ LLM-layer boundary**: which steps must be plain Python on cron (scrape/proxy-test/dedup/rank), which belong to Claude (who-to-meet, why, drafting), and the file/MCP interface between them.
- **Data contracts** for `jobs.parquet`, `shortlist.json`, `staff.parquet`, `people_to_meet.json` — propose precise schemas.
- **State & dedup** — SQLite design for `seen_jobs` / `companies_enumerated` / `people_contacted`; a job-freshness window; cross-run people dedup.
- **Scheduling** — OS scheduler (launchd/cron) for the scrape vs a Claude Desktop *local* scheduled task for judgment; why cloud routines can't reach local proxies/browser.
- **Observability** — run-logs, funnel metrics, failure surfacing.
Provide a labeled architecture **diagram** (mermaid `flowchart TB`).

## Part 4 — 2026 gotchas
The concrete things that break a build: selector rot, LinkedIn challenge/ban signals, proxy blocklisting of datacenter ranges, MCP context-bloat from verbose tool responses, parquet/pydantic version traps, captcha walls.

## Output specification
Target **6,000–10,000 words**. Use tables for the component audit and the build-vs-reuse matrix. Inline citations + a `## References` section with URLs and last-verified dates. One mermaid architecture diagram tagged `<!--FIG:reference_architecture|End-to-end pipeline: deterministic core vs Claude judgment layer-->`.

## Critical reminders
- Name specific repos, versions, commit recency, issue themes — never "review the relevant tools."
- Distinguish **JobSpy (proxied, public)** from **StaffSpy/linkedin-mcp (own IP, logged in, no proxy)** — they have opposite proxy postures.
- Flag anything volatile (free tiers, ToS, selector validity) as time-sensitive with a last-verified date.
- This is for a **single individual at low/human volume**, not an SDR-at-scale operation — weight recommendations accordingly.
