# Outreach draft quality rubric (LLM-judge, v1)

The ONLY non-code scorer in the Evaluation Plan. Judges a `draft_outreach` result for a
golden person. Versioned; align to a human spot-check before trusting at scale.

**Pass = ALL of the following are true (binary).** Score the draft 1 (pass) / 0 (fail) per item;
overall pass requires items 1–5 all true. Target ≥ 8/10 golden persons pass.

1. **References the specific warmth signal.** The body explicitly mentions the matched
   shared-ground hook (e.g. the shared school/employer named in the person's `why[]`) — not a
   generic compliment. *(Fail if it could be sent to anyone.)*
2. **Non-salesy, curiosity framing.** Asks to learn from them ("how did you move from X to Y")
   rather than "expand my network" / "exploring opportunities" / any pitch. No ask for a job.
3. **Clear, bounded coffee ask.** Requests a short, specific conversation (~20 minutes), with
   flexible scheduling. No vague "let's connect sometime".
4. **Length + channel discipline.** ≤ ~100 words for a DM (≤ ~300 chars for a connection note);
   matches the configured channel. Concise, mobile-readable, first sentence is the hook.
5. **No compliance violation.** Draft-only (never asserts it was sent); if email, targets a
   corporate domain and carries an opt-out line; no personal-address cold email.

**Informational (not pass/fail), reported for tuning:**
- Warmth-signal correctly the *highest* one in `why[]`?
- Tone natural / human (not "AI slop")?

**Judge prompt skeleton** (version: v1, 2026-06-27):
> You are grading a single coffee-chat outreach draft. Given the person's profile, their
> `why[]` warmth signals, and the draft, return JSON `{item1..item5: bool, overall: bool,
> notes: str}` strictly applying the 5 criteria above. Be strict: when unsure, fail.

Code pre-checks (run before the judge, hard-fail short-circuits): `word_count` within bound;
`warmth_signal_used` non-empty and present in the person's `why[]`; `sent == false`;
channel ∈ allowed; if email, `is_corporate_email == true`.
