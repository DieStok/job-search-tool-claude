"""Structured run-logging + the funnel metric (observability-by-default).

Every stage appends one JSON line to data/runs/<ts>.jsonl describing what it did
(stage, counts in/out, source, duration, proxy/provider used, dedup hits). Tests
inspect these events; `lcp doctor` summarizes the last run. The funnel metric
(jobs -> shortlist -> companies -> people -> to_meet -> drafts) is derived from
the recorded events so you can SEE the pipeline working (GOAL §7 evidence).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RunLogger:
    """Append-only JSONL logger scoped to a single run-log directory."""

    def __init__(self, run_log_dir: str | Path):
        self.dir = Path(run_log_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = self.dir / f"{self.run_id}.jsonl"

    def event(self, stage: str, **fields: Any) -> None:
        """Record a stage event. Never logs secrets — caller passes only safe fields."""
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "stage": stage, **fields}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")

    def timed(self, stage: str, **fields: Any) -> "_Timer":
        return _Timer(self, stage, fields)


class _Timer:
    def __init__(self, logger: RunLogger, stage: str, fields: dict):
        self.logger, self.stage, self.fields = logger, stage, fields

    def __enter__(self):
        self._t0 = time.monotonic()
        return self

    def __exit__(self, *exc):
        dur = round(time.monotonic() - self._t0, 3)
        ok = exc[0] is None
        self.logger.event(self.stage, duration_s=dur, ok=ok,
                          error=(str(exc[1]) if exc[1] else None), **self.fields)
        return False  # never swallow


def latest_run(run_log_dir: str | Path) -> Path | None:
    files = sorted(Path(run_log_dir).glob("*.jsonl"))
    return files[-1] if files else None


def funnel(run_log_dir: str | Path) -> dict[str, int]:
    """Aggregate the latest run's events into the pipeline funnel counts."""
    latest = latest_run(run_log_dir)
    counts = {"jobs_fetched": 0, "shortlisted": 0, "companies": 0,
              "people": 0, "people_to_meet": 0, "drafts": 0}
    if not latest:
        return counts
    key = {
        "fetch_jobs": "jobs_fetched", "rank_jobs": "shortlisted",
        "fetch_staff": "people", "score_people": "people_to_meet",
        "draft_outreach": "drafts",
    }
    for line in latest.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        k = key.get(rec.get("stage", ""))
        if k and isinstance(rec.get("count_out"), int):
            counts[k] += rec["count_out"]
        if rec.get("stage") == "fetch_staff" and isinstance(rec.get("company_count"), int):
            counts["companies"] += rec["company_count"]
    return counts
