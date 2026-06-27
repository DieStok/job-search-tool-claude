"""Typed data contracts for every artifact that flows between pipeline stages.

These pydantic models are the single source of truth for the shapes in the
source plan §5. Every stage validates its output against one of these, so an
untyped dict never crosses a stage boundary (GOAL AC-002).

Edges:
    fetch_jobs  -> JobPost            (jobs.parquet)
    rank_jobs   -> ShortlistEntry     (shortlist.json)
    fetch_staff -> Staff              (staff.parquet)
    score_people-> PersonToMeet       (people_to_meet.json)
    enrich      -> ContactInfo        (attached to PersonToMeet)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

ContactStatus = Literal["new", "enriched", "drafted", "contacted", "replied", "skip"]


class JobPost(BaseModel):
    """One job from a board (the jobs.parquet row contract)."""

    job_id: str                      # natural key: f"{source}:{board_id or url-hash}"
    title: str
    company: str
    company_url: str | None = None
    location: str | None = None
    remote: bool | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    date_posted: date | None = None
    job_url: str
    description: str | None = None
    job_level: str | None = None
    company_industry: str | None = None
    source: str                      # board: linkedin/indeed/glassdoor/google/adzuna/...
    first_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ShortlistEntry(BaseModel):
    """A ranked job (shortlist.json element).

    ``relevant`` and ``relevance_terms`` are populated by rank_jobs when
    ``jobs.relevance.enabled`` is true.  Both fields are None/[] when the
    relevance filter is disabled, so downstream consumers must handle that.
    See lcp/rank_jobs.py and config/config.example.yaml for allowed values.
    """

    job_id: str
    score: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    title: str | None = None
    company: str | None = None
    # Relevance annotation (populated when jobs.relevance.enabled = true).
    # relevant=True  → job matched at least one include_any term (and no exclude_any term).
    # relevant=False → job matched no include terms OR matched an exclude_any term.
    # relevant=None  → relevance filter was disabled; no keyword pass was run.
    relevant: bool | None = None
    # The specific include_any terms that matched (empty when relevant is None or False
    # due to exclusion; exclusion terms are not listed here — they are implicit).
    relevance_terms: list[str] = Field(default_factory=list)


class Education(BaseModel):
    school: str
    degree: str | None = None
    field: str | None = None
    years: str | None = None


class Experience(BaseModel):
    company: str
    title: str | None = None
    years: str | None = None


class Staff(BaseModel):
    """A person at a company (staff.parquet row contract)."""

    company: str
    name: str
    title: str | None = None
    profile_url: str                 # natural key for people dedup
    location: str | None = None
    education: list[Education] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    email: str | None = None         # only present for your own connections (StaffSpy)
    contactable: bool = False
    source: str = "staffspy"         # staffspy | linkedin_mcp


class ContactInfo(BaseModel):
    """A verified way to reach someone (from the enrichment waterfall)."""

    email: str | None = None
    phone: str | None = None
    verified: bool = False
    provider: str | None = None      # which waterfall step produced the hit
    is_corporate_email: bool | None = None   # drives the cold-email compliance gate


class PersonToMeet(BaseModel):
    """A ranked person worth a coffee (people_to_meet.json element)."""

    name: str
    company: str
    profile_url: str
    title: str | None = None
    why: list[str] = Field(default_factory=list)     # cited warmth signals (AC-021)
    warmth_score: float = Field(ge=0.0, le=1.0)
    contact_status: ContactStatus = "new"
    contact: ContactInfo | None = None


class OutreachDraft(BaseModel):
    """A coffee-chat draft (never a send side-effect in draft_only mode)."""

    person_profile_url: str
    channel: Literal["linkedin_dm", "linkedin_connect", "email"]
    subject: str | None = None       # email only
    body: str
    warmth_signal_used: str          # the specific shared-ground hook referenced
    word_count: int
    sent: bool = False               # always False in draft_only mode
