"""D4 / AC-031 — draft_outreach: references the signal, bounded, never sends, compliance-gated."""

from __future__ import annotations

from lcp.config import load_config
from lcp.contracts import ContactInfo, PersonToMeet
from lcp.outreach import _BANNED, draft_outreach
from lcp.paths import repo_root

CFG = load_config(repo_root() / "config" / "config.example.yaml")


def _person(**kw):
    base = dict(name="Alice Smith", company="TechCorp", profile_url="https://li/alice",
                why=["shared school: University of Amsterdam"], warmth_score=0.9)
    base.update(kw)
    return PersonToMeet(**base)


def test_references_top_warmth_signal():
    d = draft_outreach(CFG, _person())
    assert "University of Amsterdam" in d.body
    assert d.warmth_signal_used == "shared school: University of Amsterdam"


def test_never_sent_and_within_word_budget():
    d = draft_outreach(CFG, _person())
    assert d.sent is False
    assert d.word_count <= CFG.get("outreach.message_max_words")


def test_curiosity_framing_no_banned_phrases():
    d = draft_outreach(CFG, _person())
    low = d.body.lower()
    assert not any(b in low for b in _BANNED)
    assert "curious" in low or "how you got into" in low


def test_personal_email_is_not_cold_emailed():
    """Channel must NOT be email when only a personal address exists (compliance red line)."""
    p = _person(contact=ContactInfo(email="alice@gmail.com", is_corporate_email=False, verified=True))
    d = draft_outreach(CFG, p)
    assert d.channel == "linkedin_dm"   # blocked from email -> DM


def test_default_channel_is_linkedin_dm():
    d = draft_outreach(CFG, _person())
    assert d.channel == "linkedin_dm"   # channel_preference: linkedin_dm_first
