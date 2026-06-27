# PROMPT D — GDPR / Dutch-law legality of cold 1:1 networking outreach + contact enrichment by an individual in NL/EU

You are a **data-protection & ePrivacy specialist** with expertise in:
1. The GDPR (Regulation (EU) 2016/679) and its Dutch implementation (UAVG), especially Article 6(1)(f) legitimate interest and the Legitimate Interest Assessment (LIA / balancing test).
2. The ePrivacy Directive (2002/58/EC) as implemented in the Netherlands via the **Telecommunicatiewet** (Telecomwet, esp. art. 11.7) governing unsolicited electronic communications, enforced by the **ACM**.
3. The practical compliance posture for individuals (not enterprises) doing 1:1 professional networking, and the contact-data-enrichment industry's GDPR exposure (Apollo, Hunter, Dropcontact, Kaspr).

This is the **load-bearing legal-grounding** report for a tool an **individual** in **Amsterdam** will use to: enrich a handful of professional contacts' email/phone (via free-tier providers), then send **cold, 1:1, informational "coffee-chat" requests** (LinkedIn DM and/or email) to people at companies they're interested in working for. This is *not* a sales/marketing operation and *not* bulk — it's a job-seeker networking, low volume, human-paced. The output must let the builder encode safe defaults and write an honest `COMPLIANCE.md`. **This is an engineering grounding note, NOT legal advice; say so, and flag where a lawyer is genuinely needed.**

> **CENTRAL RESEARCH QUESTION:** Under GDPR + Dutch law (UAVG + Telecomwet/ePrivacy), what may an **individual** lawfully do when (a) **enriching** a professional contact's email/phone from third-party providers and (b) sending a **cold 1:1 informational coffee-chat** message by **LinkedIn DM** and by **email** — and what concrete defaults, filters, and disclosures keep that safe?

Decompose into:
1. The lawful-basis analysis for **holding/enriching** the data (GDPR).
2. The lawful-basis analysis for **sending** the message (ePrivacy/Telecomwet), per channel.
3. The B2B-vs-consumer / corporate-vs-personal-address distinction (the decisive axis).
4. A concrete, defaults-level do/don't checklist + what to put in `COMPLIANCE.md`.

## Part 1 — Holding & enriching the data (GDPR)
- Is **legitimate interest (Art 6(1)(f))** an appropriate basis for an individual job-seeker to obtain a contact's professional email/phone for 1:1 networking? Walk the **three-part LIA**: purpose test, necessity test, balancing test — with the specifics of this use case.
- Data-subject **transparency** (Art 13/14) when data is obtained indirectly (from an enrichment provider): what notice, when, and is the "disproportionate effort" exemption available for 1:1 outreach?
- **Purpose limitation & storage limitation** (Art 5): how long may enriched data be kept; delete-after-purpose defaults.
- Data-subject **rights** (access, objection, erasure) the individual must honor, and how a single user realistically does so.
- The enrichment **providers' own** GDPR posture and how it flows to the user: Dropcontact (no stored DB, CNIL), Kaspr (French, Art 6(1)(f) documented, Bloctel), vs US-parented Apollo/Hunter (EU-US Data Privacy Framework certification). Does using a non-compliant source create liability for the user?
**Search for:** "GDPR legitimate interest B2B contact enrichment individual 2026", "AVG/UAVG persoonsgegevens verrijken legitiem belang", "Article 14 disproportionate effort indirect collection cold outreach", "EU-US Data Privacy Framework Apollo Hunter certified".

## Part 2 — Sending the message (ePrivacy / Telecomwet), per channel
- **Email:** Telecomwet art 11.7 — when is prior consent required vs the legitimate-interest/soft-opt-in path? Does the **B2B exemption** apply in NL, and to whom exactly?
- **LinkedIn DM / connection note:** is a platform DM an "electronic communication" under Telecomwet, or outside its push-channel scope? What does LinkedIn's *own* User Agreement permit/forbid for unsolicited messaging and automation, independent of statute?
- **Opt-out / unsubscribe** obligations for 1:1 messages; right-to-object mechanics.
- Who **enforces** (ACM vs AP/Autoriteit Persoonsgegevens) and what realistic exposure does a low-volume individual face?
**Search for:** "Telecomwet 11.7 spam B2B uitzondering 2026", "ACM ongevraagde communicatie zakelijk", "LinkedIn User Agreement unsolicited messages automation 2026", "cold email Netherlands legal B2B 2026".

## Part 3 — The decisive axis: corporate vs personal, B2B vs natural person
- Build the decision: corporate-domain address at a registered legal entity (BV/NV) → B2B path; personal address / freelancer-natural-person → consumer path requiring consent. Where do sole traders (eenmanszaak/ZZP) fall? How to operationalize a **target filter** that only cold-emails corporate domains.
- The LinkedIn-DM path as the **lower-exposure default** for first contact, and why.

## Part 4 — Concrete defaults + `COMPLIANCE.md` content
Produce:
- A **do / don't checklist** at the level of software defaults (target filters, daily caps, opt-out text, retention windows, LIA-on-file).
- A **one-paragraph LIA template** the user can keep on file per outreach batch.
- A **suggested opt-out line** for cold emails.
- A short list of **red lines** that should be hard-blocked in software (e.g. never cold-email a personal/consumer address; honor objection immediately).
- An explicit "**when to consult a lawyer**" boundary.

## Output specification
Target **5,000–8,000 words**. Plain, decision-oriented language. Inline citations to statute/regulator guidance + a `## References` section (GDPR/UAVG/Telecomwet articles, ACM/AP guidance, DLA Piper/Linklaters NL guides). One mermaid decision-tree diagram tagged `<!--FIG:outreach_legality_decision|Decision tree: may I enrich + may I send, by channel and contact type, in NL/EU-->`.

## Critical reminders
- This is for an **individual at low volume**, not a company at scale — calibrate the risk realistically (don't over- or under-state).
- Keep the **GDPR (hold/enrich)** analysis distinct from the **ePrivacy/Telecomwet (send)** analysis — they are separate gates.
- The **corporate-vs-personal-address** distinction is the load-bearing axis — make it operational.
- Label everything **engineering grounding, not legal advice**, and name the few points where a lawyer is genuinely warranted.
- Cite Dutch statute/regulator sources specifically, not just generic EU GDPR blogs.
