"""SQLite state: seen_jobs, companies_enumerated, people_contacted (AC-003).

Purpose: never re-scrape a seen job, never double-enumerate a company, never
double-draft/contact a person. Idempotent upserts; WAL mode for safe concurrent
read while a scheduled job writes.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    job_id      TEXT PRIMARY KEY,
    title       TEXT,
    company     TEXT,
    job_url     TEXT,
    source      TEXT,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS companies_enumerated (
    company       TEXT PRIMARY KEY,
    company_url   TEXT,
    enumerated_at TEXT NOT NULL,
    n_staff       INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS people_contacted (
    profile_url    TEXT PRIMARY KEY,
    name           TEXT,
    company        TEXT,
    contact_status TEXT NOT NULL,
    first_seen     TEXT NOT NULL,
    contacted_at   TEXT
);
"""


class State:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.row_factory = sqlite3.Row
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---- jobs ---------------------------------------------------------------
    def is_job_seen(self, job_id: str, *, freshness_days: int | None = None) -> bool:
        """True if job_id was seen (optionally only within a freshness window)."""
        with self._conn() as c:
            row = c.execute("SELECT first_seen FROM seen_jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            return False
        if freshness_days is None:
            return True
        first_seen = datetime.fromisoformat(row["first_seen"])
        return datetime.now(timezone.utc) - first_seen <= timedelta(days=freshness_days)

    def record_job(self, job_id: str, *, title="", company="", job_url="", source="") -> bool:
        """Upsert a job. Returns True if it was NEW (not previously seen)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            existing = c.execute("SELECT 1 FROM seen_jobs WHERE job_id=?", (job_id,)).fetchone()
            if existing:
                c.execute("UPDATE seen_jobs SET last_seen=? WHERE job_id=?", (now, job_id))
                return False
            c.execute(
                "INSERT INTO seen_jobs (job_id,title,company,job_url,source,first_seen,last_seen)"
                " VALUES (?,?,?,?,?,?,?)",
                (job_id, title, company, job_url, source, now, now),
            )
            return True

    # ---- companies ----------------------------------------------------------
    def is_company_enumerated(self, company: str) -> bool:
        with self._conn() as c:
            return c.execute(
                "SELECT 1 FROM companies_enumerated WHERE company=?", (company,)
            ).fetchone() is not None

    def record_company(self, company: str, *, company_url="", n_staff=0) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as c:
            c.execute(
                "INSERT INTO companies_enumerated (company,company_url,enumerated_at,n_staff)"
                " VALUES (?,?,?,?) ON CONFLICT(company) DO UPDATE SET"
                " enumerated_at=excluded.enumerated_at, n_staff=excluded.n_staff",
                (company, company_url, now, n_staff),
            )

    # ---- people -------------------------------------------------------------
    def person_status(self, profile_url: str) -> str | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT contact_status FROM people_contacted WHERE profile_url=?", (profile_url,)
            ).fetchone()
        return row["contact_status"] if row else None

    def is_person_contacted(self, profile_url: str) -> bool:
        """True once a person has been drafted/contacted/replied (never re-draft)."""
        status = self.person_status(profile_url)
        return status in {"drafted", "contacted", "replied"}

    def record_person(self, profile_url: str, *, name="", company="", status="new") -> None:
        now = datetime.now(timezone.utc).isoformat()
        contacted_at = now if status in {"contacted", "replied"} else None
        with self._conn() as c:
            c.execute(
                "INSERT INTO people_contacted (profile_url,name,company,contact_status,first_seen,contacted_at)"
                " VALUES (?,?,?,?,?,?) ON CONFLICT(profile_url) DO UPDATE SET"
                " contact_status=excluded.contact_status,"
                " contacted_at=COALESCE(excluded.contacted_at, people_contacted.contacted_at)",
                (profile_url, name, company, status, now, contacted_at),
            )

    def counts(self) -> dict[str, int]:
        with self._conn() as c:
            return {
                "seen_jobs": c.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0],
                "companies_enumerated": c.execute("SELECT COUNT(*) FROM companies_enumerated").fetchone()[0],
                "people_contacted": c.execute(
                    "SELECT COUNT(*) FROM people_contacted WHERE contact_status!='new'"
                ).fetchone()[0],
            }
