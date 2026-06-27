"""D1 / AC-002 — typed contracts exist and round-trip."""

from __future__ import annotations

import json

from lcp.contracts import (
    ContactInfo,
    Education,
    JobPost,
    OutreachDraft,
    PersonToMeet,
    ShortlistEntry,
    Staff,
)


def test_jobpost_roundtrip():
    j = JobPost(job_id="linkedin:123", title="Data Engineer", company="Acme",
                job_url="https://x/y", source="linkedin")
    blob = j.model_dump_json()
    j2 = JobPost.model_validate_json(blob)
    assert j2.job_id == "linkedin:123" and j2.source == "linkedin"


def test_shortlist_score_bounds():
    e = ShortlistEntry(job_id="linkedin:1", score=0.8, reasons=["role match"])
    assert 0 <= e.score <= 1
    try:
        ShortlistEntry(job_id="x", score=1.5)
        raise AssertionError("score >1 should be rejected")
    except Exception:
        pass


def test_staff_and_person_shapes():
    s = Staff(company="Acme", name="Jo", profile_url="https://li/jo",
              education=[Education(school="UvA")])
    assert s.education[0].school == "UvA"
    p = PersonToMeet(name="Jo", company="Acme", profile_url="https://li/jo",
                     why=["shared school: UvA"], warmth_score=0.6,
                     contact=ContactInfo(email="jo@acme.nl", verified=True, provider="apollo"))
    assert p.why and p.contact.provider == "apollo"
    # serializes to the people_to_meet.json shape
    json.dumps(p.model_dump(), default=str)


def test_outreach_draft_is_never_sent_by_default():
    d = OutreachDraft(person_profile_url="https://li/jo", channel="linkedin_dm",
                      body="Hi Jo, ...", warmth_signal_used="shared school: UvA", word_count=42)
    assert d.sent is False
