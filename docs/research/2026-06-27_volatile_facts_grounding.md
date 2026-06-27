# LinkedIn Networking & Job Pipeline — Volatile Facts Grounding Report
**Research date: 2026-06-27 | Source: research-analyst subagent (claude-sonnet-4-6), multi-source web**

> This report resolves the time-sensitive §10 research items of the source plan. Its
> BASELINE RECOMMENDATION yaml blocks are folded directly into `config/config.example.yaml`
> and `docs/COMPLIANCE.md`. Treat every figure as last-verified 2026-06-27; re-check before relying.

---

## Section 1: Enrichment Free Tiers, MCP Connectors, LinkedIn/Phone Support

- **Apollo.io** — Free: ~unlimited email (fair-use ~250/day) + 5 mobile + 10 export + 50 AI credits/mo (restructured late 2025). **Native hosted MCP** `https://mcp.apollo.io/mcp` (OAuth via Claude Desktop Connectors, no local install, works on free plan). Apollo docs recommend **"Approval required"** for credit-consuming tools. LinkedIn-URL→email: yes. Phone: yes. Conf: High.
- **Hunter.io** — Free: 50 unified credits/mo. Native MCP but local `hunter-io/hunter-mcp` **deprecated/archived** → moving to a Remote MCP Server (endpoint stabilizing). Email-only, no phone. Conf: High (credits) / Med (remote URL).
- **Prospeo** — Free: 75 email + 100 extension credits/mo. **Truly native** hosted MCP `https://mcp.prospeo.io` (OAuth2 or API key custom connector). LinkedIn-URL→email: yes. Phone: paid only. Conf: High.
- **LeadMagic** — 100 **one-time** signup credits (NOT recurring). No native/Composio MCP found. LI→email yes; phone paid. Conf: Med.
- **Findymail** — ~10 credits/mo (trial-grade). No MCP. Email only. Conf: Med.
- **ContactOut** — 5 lookups/day. No MCP. LI-first; phone yes. Conf: Med.
- **RocketReach** — 5 lookups/mo. No MCP. LI→email + reverse; phone yes. Conf: High (credits).
- **Dropcontact** — **No true free plan** (paid ~€24/mo, 500 enrich). Algorithmic, **no stored DB**, strongest GDPR posture (CNIL). No MCP. Email only (no phone). Conf: High (GDPR) / Med (free tier likely none).
- **Kaspr** — Free: 15 B2B email + 5 phone + 5 direct + 10 export credits/mo. **MCP live for all plans.** French/CNIL, Art 6(1)(f) documented. LI→email + phone yes. Conf: High.
- **Derrick** — Free: 100 credits/mo recurring (Sheets/ext/API/MCP shared). **Native MCP.** LI→email yes (89% hit claim). Phone unconfirmed free. Conf: Med-High.

**BASELINE:**
```yaml
enrichment_primary: apollo            # native MCP, free, confirmation-gated, phone + email
enrichment_secondary: prospeo         # 75/mo, native MCP mcp.prospeo.io, LI-URL→email
enrichment_gdpr_preferred: kaspr      # EU/French, MCP live, phone, 15 email free
enrichment_email_only_backup: hunter  # 50/mo, native (remote) MCP, email only
enrichment_skip: [leadmagic, findymail, contactout, rocketreach]  # no MCP / trivial free tier
dropcontact_use_case: gdpr_purist_email_only_paid
```

## Section 2: Which Enrichment MCPs Work in Claude Desktop Today
- **Apollo — CONFIRMED.** Settings→Connectors→Add URL `https://mcp.apollo.io/mcp`→OAuth. Free plan OK. Set credit tools to **"Approval required"**.
- **Prospeo — CONFIRMED native.** Custom remote connector `https://mcp.prospeo.io`.
- **Hunter — works, transition.** Deprecated local server still installs via API key; remote endpoint stabilizing.
- **Kaspr — confirmed via help docs** (MCP live all plans).
- **Derrick — confirmed** native MCP w/ free credits.
- **LeadMagic / Findymail / ContactOut / RocketReach / Dropcontact — no working CD MCP.**

**BASELINE:**
```yaml
mcp_stack_claude_desktop: [apollo, prospeo, kaspr, hunter]
apollo_confirmation_gate: "Approval required"  # MANDATORY — prevents silent credit burn
```

## Section 3: GDPR / Netherlands legality (cold 1:1 outreach + enrichment)
- **Two frameworks:** GDPR/UAVG (Art 6(1)(f) legitimate interest + a documented LIA) governs holding/processing data; **Telecomwet Art 11.7** (ePrivacy, enforced by ACM) governs *sending* electronic comms.
- **B2B (corporate email at a registered entity):** cold email permitted under legitimate interest if genuine, targeted (not bulk), with opt-out + documented LIA. LinkedIn DM falls largely outside Telecomwet's push-channel scope; GDPR still applies to the data behind finding the contact. 1:1 informational outreach = low risk.
- **Natural persons / consumers / freelancers (personal address, no BV/NV):** **prior explicit consent required** for commercial electronic comms. `@gmail.com`/personal-domain = consent needed.
- **ePrivacy overrides** GDPR for the sending channel — even if you may hold the data, Telecomwet governs whether you may send.
- **EU-friendlier sources:** Dropcontact (no stored DB; lowest exposure) > Kaspr (French/CNIL) > US providers (Apollo/Hunter DPF-certified, higher diligence burden).
- **DO:** target corporate domains; write a 1-paragraph LIA; include opt-out; 1:1 personalized (not mail-merge); prefer LinkedIn DM for first contact; honor opt-outs immediately; prefer Dropcontact/Kaspr data. **DON'T:** cold-email personal/consumer addresses w/o consent; bulk (>~20/day); store data beyond purpose; assume "works for sales" = "legal for an individual in NL".

**BASELINE:**
```yaml
outreach_channel_preference: linkedin_dm_first   # lower Telecomwet exposure than email
cold_email_target_filter: corporate_domain_only  # @company.nl not personal domains
enrichment_provider_eu: [dropcontact, kaspr]
lia_required: true
opt_out_required: true
max_daily_outreach: 20
```

## Section 4: StaffSpy current state (mid-2026)
- `cullenwatson/StaffSpy` ~257★, latest **v0.2.25 (Jan 2025)** — maintenance slowed. Runs on own logged-in IP; results depend heavily on account quality (seasoned 500+ conn, verified email → far fewer "hidden member" blanks).
- `session_file="session.pkl"` supported (cookies ~1 week). Captcha: `solver_service` (CapSolver/2Captcha) + `solver_api_key`; **FuncCAPTCHA** issues reported (CapSolver flaky → prefer 2Captcha / browser login). Self-terminates when actively blocked.
- No confirmed selector breakage in current release, but no release since Jan 2025 → DOM changes since may need a fork/patch.
- Realistic limits: community **50–150/day**; recommend <100/day, 5–10s delays.

**BASELINE:**
```yaml
staffspy_session_file: "session.pkl"
staffspy_captcha_solver: "2captcha"     # CapSolver unreliable for FuncCAPTCHA
staffspy_max_per_company_per_day: 75
staffspy_inter_request_delay_sec: 8
staffspy_account_requirement: seasoned  # verified email, 500+ connections, 6+ months
```

## Section 5: JobSpy NL/EU breadth
- Supported boards: `linkedin, indeed, glassdoor, google, zip_recruiter, bayt, bdjobs`. `country_indeed="Netherlands"` supported (Indeed is #1 NL jobs site); Glassdoor NL too. LinkedIn global via `location`; **rate-limits ~page 10 / single IP → proxies "basically a must"**. `proxies=['user:pass@host:port', ...]` round-robin.
- **Adzuna API** supports NL (free tier, register at developer.adzuna.com; ~limited/rate-limited) — worth adding as supplement. Community `adzuna-job-search-mcp` exists. **Coresignal:** paid only, skip.

**BASELINE:**
```yaml
jobspy_site_names: [linkedin, indeed, glassdoor, google]
jobspy_country_indeed: "Netherlands"
jobspy_proxies_required_for_linkedin: true   # residential only
adzuna_supplement: true
coresignal: skip
```

## Section 6: linkedin-mcp-server (stickerdaniel) — can it replace StaffSpy?
- `stickerdaniel/linkedin-mcp-server` **2,500★**, **v4.16.1 (2026-06-26)** — actively maintained (daily releases). 16 tools incl. `get_person_profile` (experience/education/skills/**contact_info**/certs/posts), `get_company_employees`, `search_people/jobs`, `get_inbox`/`send_message`/`get_feed`. Auth = own browser session (import from Chrome/Brave/Edge/Safari via `--login`); no API key.
- **Verdict:** YES for **low volume (≤50/day)** people lookups — richer than StaffSpy, active, and exposes messaging. NOT for batch 500+ (synchronous per-call). Use StaffSpy for batch company staff; linkedin-mcp for interactive lookups + drafting + inbox.

**BASELINE:**
```yaml
linkedin_mcp: stickerdaniel/linkedin-mcp-server   # v4.16.1, active; people-layer for ≤50/day
people_layer_default: linkedin_mcp                # interactive, low-volume default
staffspy_use_case: batch_company_staff_scraping   # when you need >50 profiles/run
linkedin_mcp_daily_max: 50
```

## Section 7: Cheapest proxy path
- **Datacenter (Webshare DC) & free pools (jhao104/proxy_pool): NEVER for LinkedIn** — blocked on ASN. Webshare itself says DC "doesn't work on LinkedIn".
- **JobSpy LinkedIn (unauthenticated):** rotating **residential** works — Webshare residential ~$0.99–1.40/GB (1–3 GB/mo ≈ $2–4 for a personal search). Bright Data $8.40/GB PAYG (overkill).
- **StaffSpy / linkedin-mcp (authenticated):** **own home IP, no proxy** (proxy on a logged-in session raises detection). If you must, ISP static proxies, not rotating residential.

**BASELINE:**
```yaml
proxy_jobspy_linkedin: webshare_residential   # ~$1.40/GB; rotating; UNAUTHENTICATED only
proxy_staffspy: none                          # own home IP
proxy_linkedin_mcp: none                       # browser session = own IP; never proxy logged-in
proxy_datacenter: never
proxy_free_pool: never
```

## Section 8: Account safety pacing (2026)
- **StaffSpy:** medium-high risk at volume (programmatic login → FuncCAPTCHA). 50–100/day, 5–10s delays, never parallel on one account, seasoned account.
- **linkedin-mcp:** lower risk (real browser cookies). ~100–150 profile views/day; **30–60s between sequential lookups**; 10–20 connects/day; 15–20 msgs/day; connect ceiling ~100/week (stay ≤50).
- **General:** human hours (08:00–21:00 local), stop 48–72h on challenge, keep organic manual activity.

**BASELINE:**
```yaml
staffspy_max_profiles_per_day: 75
staffspy_delay_between_requests_sec: 8
linkedin_mcp_max_profiles_per_day: 100
linkedin_connection_requests_per_week: 50
linkedin_messages_per_day: 15
automation_hours: "08:00-21:00"   # Amsterdam local
pause_on_captcha_hours: 48
```

## Section 9: Cold coffee-chat reply-rate patterns (for the drafting prompt)
- Benchmarks: generic cold ~5–6% accept; personalized ~9–10%; strong-personalization DM 18–25%; coffee-chat **with prior content engagement 40–60%**; cold w/o context <15%.
- **Tip 1 — micro-engage first** (like/comment a recent post; wait 24h) ~doubles accept (8%→14%).
- **Tip 2 — <100 words (<300 char for connect note); specific hook in sentence 1** referencing their content/role transition (3× reply vs template).
- **Tip 3 — bounded time ask** ("20 minutes, no prep", flexible scheduling).
- **Tip 4 — curiosity framing** ("how did you move from X to Y") not "expand my network"/"exploring opportunities".
- **Tip 5 — 1 person/company at a time;** send **Tue–Wed 09:00–12:00 CET**. Email subject 8–10 words, <50 chars, specific.

**BASELINE:**
```yaml
outreach_sequence:
  step_0: engage_content_first      # like/comment their post; wait 24h
  step_1: connect_with_note          # <300 chars; specific hook; coffee framing
  step_2: follow_up_dm_if_connected  # 72h later if no reply; <100 words
message_max_words: 100
ask_framing: curiosity_not_networking
time_commitment: "20 minutes"
send_window: "Tue-Wed 09:00-12:00 CET"
target_per_company: 1
```

---
*Proxycurl excluded (dead July 2025). Full source URLs retained in the original subagent transcript.*
