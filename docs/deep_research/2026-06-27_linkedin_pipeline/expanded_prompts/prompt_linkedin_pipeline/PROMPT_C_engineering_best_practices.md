# PROMPT C — Per-component engineering best-practices for a local scraping + enrichment + MCP pipeline

You are a **principal engineer** specializing in resilient data-collection systems, with expertise in:
1. Web-scraping resilience & anti-detection (request pacing, fingerprinting, session reuse, backoff).
2. Proxy infrastructure (rotation, health-checking, residential vs datacenter economics).
3. Durable local pipelines (SQLite state design, idempotency, dedup, observability) and secure local secrets handling.
4. MCP server security and human-in-the-loop confirmation patterns.

You are writing the **best-practices reference** that the build plans of a local LinkedIn networking pipeline will cite. The system: deterministic Python core (JobSpy with rotating proxies for public job search; StaffSpy on the user's own logged-in IP, no proxy, for staff on selected companies; dedup/rank in SQLite; cron/launchd scheduled) + a Claude Desktop MCP layer (judgment + drafting, confirmation-gated). Single user, Amsterdam, low/human volume — account-safety and correctness matter far more than throughput.

> **CENTRAL RESEARCH QUESTION:** What are the current (2026) engineering best-practices for each component of this pipeline, expressed concretely enough to drop into a build plan as cited requirements?

Cover each area below. For each: the **principle**, the **concrete how** (parameters, code-shape, thresholds), and the **failure mode it prevents** — with citations.

## 1. Scraping resilience & account safety
- Human-pacing: realistic request rates / delays / jitter for LinkedIn authenticated reads (StaffSpy, linkedin-mcp) before challenges/bans; daily ceilings; session warm-up.
- Public job-board scraping (JobSpy): per-IP page caps, rotating user-agents, when datacenter IPs suffice vs need residential.
- Persistent session reuse (cookie/session_file) vs captcha solvers — trade-offs.
- Graceful degradation when a board returns 0 / a selector breaks (per-source isolation).
**Search for:** "LinkedIn scraping rate limit ban 2026", "human pace requests per day LinkedIn account safety", "StaffSpy delay settings".

## 2. Proxy rotation & health-checking
- Test-and-discard model: probe each proxy against a *real* target request, keep unblocked, treat as disposable.
- Gateway patterns: a single rotating endpoint (Scrapoxy/mitmproxy addon) vs in-process rotation — pros/cons.
- Datacenter vs residential economics for *public* LinkedIn job search at low-moderate volume; rough current pricing (Webshare datacenter, a residential entry tier, Bright Data PAYG). Does the public JobSpy endpoint even need residential?
- Free-pool reality (jhao104/proxy_pool): viability + quality caveats.
**Search for:** "Webshare datacenter proxy pricing 2026", "residential proxy cost per GB 2026", "proxy health check rotating gateway design".

## 3. State, dedup & idempotency (SQLite)
- Schema design for `seen_jobs` / `companies_enumerated` / `people_contacted`; natural keys for jobs (board+id vs url) and people (profile_url); first_seen/last_seen; freshness windows.
- Idempotent re-runs (upsert patterns), cross-run people dedup, avoiding double-outreach.
- WAL mode, concurrency with a scheduler, backup.
**Search for:** "sqlite scraping dedup schema best practice", "idempotent etl upsert sqlite".

## 4. Enrichment-waterfall design
- Cascade ordering across providers, stop-on-verified-hit, cost/credit budgeting, caching results, verification (catch-all/bounce risk), avoiding wasted credits.
- Pluggable provider-adapter interface design.
**Search for:** "email enrichment waterfall design Clay", "contact enrichment cascade stop on hit".

## 5. MCP server security + human-in-the-loop gating
- Confirmation/elicitation patterns for risky tools (account-enumeration, credit-spend, outreach-send); read vs write tool separation; least-privilege; input validation; never logging secrets; stdio vs network exposure.
- Keeping tool responses small to avoid context bloat.
**Search for:** "MCP server security best practices 2026", "MCP elicitation confirmation human in the loop", "MCP tool least privilege".

## 6. Local scheduling & secrets
- launchd (macOS) vs cron vs a Claude Desktop local scheduled task: reliability, logging, catch-up-on-wake, when each fits; why the scrape should be decoupled from the app.
- Secrets: `.env` + OS keychain (macOS Keychain) vs plaintext; never-in-repo; key rotation; what a non-technical user can manage.
**Search for:** "launchd vs cron python job 2026", "macos keychain api keys cli", "python keyring secrets".

## Output specification
Target **6,000–9,000 words**. Heavy use of concrete numbers/thresholds/parameters and short code/config snippets. Inline citations + `## References`. One mermaid diagram tagged `<!--FIG:resilience_layers|Defense-in-depth: pacing, proxy health, state-dedup, gating layers across the pipeline-->`.

## Critical reminders
- Every recommendation must be **concrete** (a number, a parameter, a code-shape), not generic advice.
- Always distinguish the **JobSpy-proxied-public** path from the **own-IP-authenticated** path — they need opposite proxy strategies.
- Optimize for a **single low-volume user** and **account safety**, not max throughput.
- Flag volatile pricing/limits with last-verified dates.
