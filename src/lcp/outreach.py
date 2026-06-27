"""draft_outreach — a deterministic, compliance-gated coffee-chat draft composer (AC-031).

This produces a strong STARTING draft grounded in the research framing
(`eval/outreach_rubric.md`): it references the person's top warmth signal, uses curiosity
framing (not a pitch), makes a bounded ~20-minute ask, and stays within the word budget.
Claude refines it further in-conversation. **It never sends** (draft_only baseline) and
enforces the compliance red lines in code.
"""

from __future__ import annotations

from .contracts import OutreachDraft, PersonToMeet

# Phrases that betray a transactional/networking pitch — the rubric fails on these.
_BANNED = ("expand my network", "exploring opportunities", "grow my network", "job opportunity")


_HONORIFICS = {"dr", "prof", "mr", "mrs", "ms", "mx", "ir", "drs", "dhr", "mevr", "sir"}


def _first_name(name: str) -> str:
    """First name, skipping leading honorifics (Dr./Prof./Ir./…) so we don't write 'Hi Dr.'."""
    if not name:
        return "there"
    parts = [p for p in name.strip().split() if p.strip(".").lower() not in _HONORIFICS]
    return parts[0] if parts else "there"


def _word_count(text: str) -> int:
    return len(text.split())


def draft_outreach(cfg, person: PersonToMeet | dict, logger=None) -> OutreachDraft:
    """Compose a coffee-chat draft for `person`. Returns an OutreachDraft; never sends."""
    if isinstance(person, dict):
        person = PersonToMeet.model_validate(person)

    oc = cfg.get("outreach", {}) or {}
    comp = cfg.get("compliance", {}) or {}
    max_words = int(oc.get("message_max_words", 100))
    time_commitment = oc.get("time_commitment", "20 minutes")
    pref = oc.get("channel_preference", "linkedin_dm_first")

    signal = person.why[0] if person.why else f"your work at {person.company}"
    # strip a leading "shared school: " style label for natural phrasing
    signal_phrase = signal.split(":", 1)[1].strip() if ":" in signal else signal

    # ---- channel selection + compliance gate -------------------------------
    has_corp_email = bool(person.contact and person.contact.is_corporate_email and person.contact.email)
    channel = "linkedin_dm" if pref == "linkedin_dm_first" else "email"
    if channel == "email":
        # never cold-email a personal/consumer address when the red line is set
        if comp.get("block_personal_domain_cold_email", True) and not has_corp_email:
            channel = "linkedin_dm"

    first = _first_name(person.name)
    # curiosity-framed, bounded ask, references the specific shared signal.
    body = (
        f"Hi {first} — I came across your profile and noticed {signal_phrase}. "
        f"I'm genuinely curious how you got into your work at {person.company} and what it's "
        f"like there. Would you be open to a short {time_commitment} chat sometime? "
        f"Happy to work around your calendar — no prep needed."
    )

    # enforce the word budget by trimming the optional closing if needed
    if _word_count(body) > max_words:
        body = (
            f"Hi {first} — noticed {signal_phrase}. I'm curious how you got into your work at "
            f"{person.company}. Open to a {time_commitment} chat, around your calendar?"
        )

    subject = None
    if channel == "email":
        subject = f"Curious about your path at {person.company}"
        opt_out = "\n\nIf you'd rather not hear from me, just reply \"no thanks\" and I won't follow up."
        if comp.get("opt_out_required", True):
            body = body + opt_out

    draft = OutreachDraft(
        person_profile_url=person.profile_url,
        channel=channel,
        subject=subject,
        body=body,
        warmth_signal_used=signal,
        word_count=_word_count(body),
        sent=False,  # draft_only — ALWAYS false
    )
    if logger is not None:
        logger.event("draft_outreach", count_out=1, channel=channel,
                     signal=signal, words=draft.word_count)
    return draft
