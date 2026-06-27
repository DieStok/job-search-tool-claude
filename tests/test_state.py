"""D1 / AC-003 — state dedup: no re-scrape, no double-outreach."""

from __future__ import annotations

from lcp.state import State


def test_job_dedup(tmp_path):
    st = State(tmp_path / "s.sqlite")
    assert st.record_job("linkedin:1", title="DE", company="Acme") is True   # new
    assert st.record_job("linkedin:1", title="DE", company="Acme") is False  # seen -> not new
    assert st.is_job_seen("linkedin:1") is True
    assert st.is_job_seen("linkedin:2") is False


def test_job_freshness_window(tmp_path):
    st = State(tmp_path / "s.sqlite")
    st.record_job("linkedin:1")
    # recently recorded -> within a 30-day window
    assert st.is_job_seen("linkedin:1", freshness_days=30) is True
    # with no window it's simply "seen"
    assert st.is_job_seen("linkedin:1") is True


def test_company_enumeration(tmp_path):
    st = State(tmp_path / "s.sqlite")
    assert st.is_company_enumerated("Acme") is False
    st.record_company("Acme", n_staff=12)
    assert st.is_company_enumerated("Acme") is True


def test_people_no_double_outreach(tmp_path):
    st = State(tmp_path / "s.sqlite")
    url = "https://li/jo"
    st.record_person(url, name="Jo", company="Acme", status="new")
    assert st.is_person_contacted(url) is False
    st.record_person(url, status="drafted")
    assert st.is_person_contacted(url) is True   # drafted -> never re-draft
    st.record_person(url, status="contacted")
    assert st.person_status(url) == "contacted"


def test_counts(tmp_path):
    st = State(tmp_path / "s.sqlite")
    st.record_job("linkedin:1")
    st.record_company("Acme")
    st.record_person("https://li/jo", status="contacted")
    c = st.counts()
    assert c["seen_jobs"] == 1 and c["companies_enumerated"] == 1 and c["people_contacted"] == 1
