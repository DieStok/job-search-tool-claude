# Compliance & account-safety — GDPR / Dutch law for 1:1 networking

> **Engineering grounding note, NOT legal advice.** This summarizes how an
> **individual** job-seeker in the **Netherlands/EU** can use this tool for **low-volume,
> 1:1 informational coffee-chat** outreach within GDPR + Dutch ePrivacy rules. It is
> grounded in research dated 2026-06-27 (`docs/research/2026-06-27_volatile_facts_grounding.md`
> §3, deepened by the deep-research dossier in `docs/deep_research/`). For anything
> commercial, at scale, or where money/risk is material, **consult a Dutch privacy
> lawyer.** Where the deep-research GDPR report (Prompt D) lands, its decision tree and
> LIA template supersede this summary.

## Two separate legal gates

Cold 1:1 outreach passes through **two independent gates** — clearing one does not clear the other:

1. **GDPR / UAVG — may I HOLD & ENRICH this person's data?**
   Lawful basis for B2B networking is **Article 6(1)(f) legitimate interest**, which
   requires a documented **Legitimate Interest Assessment (LIA)**: purpose test
   (genuine professional reason), necessity test (is enrichment needed), balancing test
   (your interest vs. their rights). Also: **purpose limitation** + **storage limitation**
   (delete after the purpose is served), **transparency** (Art. 13/14), and honoring
   **objection/erasure** requests.

2. **ePrivacy / Telecomwet art. 11.7 — may I SEND this message, on this channel?**
   Enforced by the **ACM** (not the AP). Governs unsolicited electronic communications.
   This gate can forbid sending **even when GDPR lets you hold the data.**

## The decisive axis: corporate vs. personal address

| Contact | Channel | Rule |
|---|---|---|
| **Corporate email** at a registered entity (BV/NV), professional context | Email | **B2B path** — permitted under legitimate interest if genuine, targeted (not bulk), with an opt-out + LIA on file. |
| **Personal / consumer address** (`@gmail`, `@hotmail`, freelancer personal domain) | Email | **Consumer path — prior consent required.** Do **not** cold-email. |
| Anyone, professional context | **LinkedIn DM / connection note** | Largely **outside** Telecomwet's push-channel scope (lower exposure). GDPR still applies to the *data* used to find them. **Preferred first-contact channel.** |
| Sole trader / ZZP (eenmanszaak) | Email | Gray zone — treat as a natural person → consent. Prefer LinkedIn DM. |

## What this tool enforces in code (hard red lines)

These map to `config.compliance.*` and are enforced by the pipeline, not just documented:

- `require_human_send: true` — **the tool never auto-sends.** Claude drafts; **you** send. (Overrides `outreach.mode`.)
- `block_personal_domain_cold_email: true` — a draft to a personal/consumer email domain is **blocked**; the channel is switched to LinkedIn DM or skipped. (`ContactInfo.is_corporate_email` drives this.)
- `max_daily_outreach: 20` — proportionality + platform safety; bulk-looking volume is refused.
- `retention_days: 180` — enriched personal data is purged after this window (storage limitation).
- `opt_out_required: true` — every cold **email** carries an opt-out line.
- `lia_on_file: true` — keep a one-paragraph LIA per outreach batch (template below).
- `channel_preference: linkedin_dm_first` — lower Telecomwet exposure than email.

## Account safety (LinkedIn ToS — separate from the law)

All LinkedIn scraping is against LinkedIn's ToS; enforcement is real (Proxycurl was sued out
of existence in 2025). This is a *platform-risk* concern distinct from GDPR. Defaults
(`config.account_safety.*`, `config.people.*`), from research §4/§6/§8:

- StaffSpy / linkedin-mcp run on **your own IP, logged in, never via a proxy**.
- Pace: StaffSpy ≤ 75 profiles/company/day, 8s delays; linkedin-mcp ≤ 50/day, 30–60s between lookups.
- ≤ 50 connection requests/week; ≤ 15 messages/day; automation only 08:00–21:00 local.
- On a CAPTCHA/challenge: **stop for 48h.** Keep organic manual activity on the account.
- Prefer a **seasoned account** (verified email, 500+ connections, 6+ months) for fewer challenges.

## EU-friendlier enrichment sources

Prefer **Dropcontact** (no stored database; generates on demand; strongest CNIL posture) and
**Kaspr** (French, documented Art. 6(1)(f) balancing) for NL outreach data. US-parented
providers (Apollo, Hunter) are defensible under the EU-US Data Privacy Framework if certified,
but carry a higher diligence burden. `config.enrichment.eu_preferred` encodes this.

## LIA template (keep one per outreach batch)

> **Purpose:** I am seeking informational career conversations with professionals at
> companies relevant to my job search. **Necessity:** A direct professional contact path
> is needed to make a 1:1, non-commercial request. **Balancing:** Contact is limited to
> professional context, low volume (≤20/day), corporate channels, with an immediate
> opt-out and no onward sharing; data is deleted after {retention_days} days. The
> individual's reasonable expectations (professionals on LinkedIn expect relevant 1:1
> outreach) are not overridden. **Basis:** GDPR Art. 6(1)(f).

## Suggested opt-out line (cold email)

> *If you'd rather not hear from me, just reply "no thanks" and I won't follow up.*

## When to consult a lawyer (not optional)

- Any **commercial/sales** use, or **volume** beyond personal 1:1 networking.
- Emailing **natural persons / consumers** at all.
- Processing **special-category** data, or building any persistent **profile database**.
- If you receive an **objection, complaint, or regulator contact** — stop and get advice.
