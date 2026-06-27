#!/usr/bin/env python3
"""D6 eval/evidence runner — §7 Evaluation Plan scorer table + funnel evidence.

Runs every per-capability scorer defined in GOAL.md §7, writes:
  eval/results.md   — markdown PASS/FAIL table (one row per capability) + funnel
  eval/funnel.png   — pipeline funnel bar chart (text fallback if matplotlib absent)

Exit 0 iff ALL scorers pass.

Usage (from repo root, venv activated):
  python eval/run_eval.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NamedTuple

REPO = Path(__file__).resolve().parents[1]
EVAL_DIR = REPO / "eval"


# ---------------------------------------------------------------------------
# Scorer definitions — mirrors GOAL.md §7 table
# ---------------------------------------------------------------------------


class Scorer(NamedTuple):
    capability: str
    description: str
    pass_bar: str
    command: list[str]


SCORERS: list[Scorer] = [
    Scorer(
        "config-covers-open-questions",
        "check_config_covers_open_questions.py",
        "exit 0",
        [sys.executable, "scripts/check_config_covers_open_questions.py",
         "config/config.example.yaml"],
    ),
    Scorer(
        "eval-plan-exists",
        "gate_eval_plan_exists.py docs/GOAL.md",
        "exit 0",
        [sys.executable, "scripts/gates/gate_eval_plan_exists.py", "docs/GOAL.md"],
    ),
    Scorer(
        "ledger-exists",
        "gate_ledger_exists.py docs/LEDGER.md",
        "exit 0",
        [sys.executable, "scripts/gates/gate_ledger_exists.py", "docs/LEDGER.md"],
    ),
    Scorer(
        "contracts-valid",
        "pytest test_contracts",
        "100%",
        [sys.executable, "-m", "pytest", "-q", "tests/test_contracts.py"],
    ),
    Scorer(
        "config-options+baselines",
        "pytest test_config",
        "100%",
        [sys.executable, "-m", "pytest", "-q", "tests/test_config.py"],
    ),
    Scorer(
        "state-dedup",
        "pytest test_state",
        "100%",
        [sys.executable, "-m", "pytest", "-q", "tests/test_state.py"],
    ),
    Scorer(
        "rank-deterministic",
        "pytest test_rank_jobs",
        "100%",
        [sys.executable, "-m", "pytest", "-q", "tests/test_rank_jobs.py"],
    ),
    Scorer(
        "warmth-cites-reasons",
        "pytest test_score_people",
        "100%",
        [sys.executable, "-m", "pytest", "-q", "tests/test_score_people.py"],
    ),
    Scorer(
        "enrich-waterfall",
        "pytest test_enrich",
        "100%",
        [sys.executable, "-m", "pytest", "-q", "tests/test_enrich.py"],
    ),
    Scorer(
        "mcp-gating",
        "pytest test_mcp",
        "100%",
        [sys.executable, "-m", "pytest", "-q", "tests/test_mcp.py"],
    ),
    Scorer(
        "outreach-draft-only",
        "pytest test_outreach",
        "100%",
        [sys.executable, "-m", "pytest", "-q", "tests/test_outreach.py"],
    ),
    Scorer(
        "claude-desktop-merge",
        "pytest test_claude_desktop_config",
        "100%",
        [sys.executable, "-m", "pytest", "-q", "tests/test_claude_desktop_config.py"],
    ),
    Scorer(
        "e2e-smoke",
        "pytest test_e2e_smoke",
        "100%",
        [sys.executable, "-m", "pytest", "-q", "tests/test_e2e_smoke.py"],
    ),
    Scorer(
        "installer-idempotent",
        "scripts/test_install_dryrun.sh",
        "exit 0",
        ["bash", "scripts/test_install_dryrun.sh"],
    ),
]


# ---------------------------------------------------------------------------
# Scorer runner
# ---------------------------------------------------------------------------


class ScorerResult(NamedTuple):
    capability: str
    description: str
    pass_bar: str
    passed: bool
    exit_code: int
    duration_s: float
    stderr_snippet: str


def run_scorer(scorer: Scorer) -> ScorerResult:
    """Run a single scorer, return its result."""
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            scorer.command,
            capture_output=True,
            text=True,
            cwd=str(REPO),
            timeout=120,
        )
        passed = proc.returncode == 0
        exit_code = proc.returncode
        # Grab last 200 chars of stderr for the report notes (avoids megabytes)
        stderr_snippet = (proc.stderr or proc.stdout or "")[-200:].strip()
    except subprocess.TimeoutExpired:
        passed = False
        exit_code = -1
        stderr_snippet = "TIMEOUT after 120s"
    except FileNotFoundError as exc:
        passed = False
        exit_code = -1
        stderr_snippet = f"command not found: {exc}"
    duration_s = round(time.monotonic() - t0, 2)
    return ScorerResult(
        capability=scorer.capability,
        description=scorer.description,
        pass_bar=scorer.pass_bar,
        passed=passed,
        exit_code=exit_code,
        duration_s=duration_s,
        stderr_snippet=stderr_snippet,
    )


# ---------------------------------------------------------------------------
# Fresh golden e2e run → funnel counts
# ---------------------------------------------------------------------------


def _run_golden_funnel() -> dict[str, int]:
    """Run the full deterministic pipeline on golden data in a tmp dir.

    Returns the runlog.funnel() counts from that run. All artifacts are
    cleaned up automatically; nothing writes to the repo's data/ directory.
    """
    import json as _json
    import sys as _sys
    from datetime import date as _date
    from unittest.mock import MagicMock, patch

    import pandas as pd
    import yaml

    golden_jobs = _json.loads((REPO / "eval/golden/jobs_sample.json").read_text())
    golden_staff = _json.loads((REPO / "eval/golden/staff_sample.json").read_text())
    golden_profile = yaml.safe_load((REPO / "eval/golden/profile_sample.yaml").read_text())
    ref_date = _date(2026, 6, 27)

    from lcp import runlog
    from lcp.config import load_config
    from lcp.contracts import Staff
    from lcp.fetch_jobs import fetch_jobs
    from lcp.fetch_staff import fetch_staff, write_staff_parquet
    from lcp.mcp_server import impl_draft_outreach
    from lcp.rank_jobs import rank_jobs
    from lcp.score_people import score_people

    with tempfile.TemporaryDirectory(prefix="lcp_eval_") as tmpdir:
        tmp = Path(tmpdir)
        data_dir = tmp / "data"
        data_dir.mkdir()

        cfg = load_config(REPO / "config/config.example.yaml")
        cfg.raw["meta"]["data_dir"] = str(data_dir)
        cfg.raw["state"]["sqlite_path"] = str(tmp / "state.sqlite")
        cfg.raw["observability"]["run_log_dir"] = str(tmp / "runs")
        cfg.profile.clear()
        cfg.profile.update(golden_profile)
        cfg.raw.setdefault("jobs", {})
        cfg.raw["jobs"]["search_terms"] = ["data engineer"]
        cfg.raw["jobs"]["site_names"] = ["linkedin"]
        cfg.raw["jobs"].setdefault("adzuna", {})
        cfg.raw["jobs"]["adzuna"]["enabled"] = False
        cfg.raw.setdefault("people", {})
        cfg.raw["people"]["provider"] = "staffspy"
        cfg.raw["people"].setdefault("staffspy", {})
        cfg.raw["people"]["staffspy"]["max_profiles_per_company_per_day"] = 75
        cfg.raw["people"]["staffspy"]["inter_request_delay_sec"] = 0
        cfg.raw["people"]["staffspy"]["session_file"] = str(tmp / "session.pkl")
        cfg.raw["people"]["staffspy"]["captcha_solver"] = "none"
        cfg.raw.setdefault("people_scoring", {})
        cfg.raw["people_scoring"]["top_n_people"] = 15

        logger = runlog.RunLogger(cfg.run_log_dir)

        # Step 1: fetch_jobs (mocked JobSpy)
        df_rows = []
        for job in golden_jobs:
            parts = job["job_id"].split(":", 1)
            board_id = parts[1] if len(parts) == 2 else job["job_id"]
            df_rows.append({
                "id": board_id, "site": job["source"],
                "job_url": job["job_url"], "title": job["title"],
                "company": job["company"], "company_url": job.get("company_url"),
                "location": job.get("location"), "is_remote": job.get("remote"),
                "min_amount": job.get("salary_min"), "max_amount": job.get("salary_max"),
                "currency": job.get("salary_currency"),
                "date_posted": (
                    pd.Timestamp(job["date_posted"]) if job.get("date_posted") else None
                ),
                "description": job.get("description"),
                "job_level": job.get("job_level"),
                "company_industry": job.get("company_industry"),
            })
        jobspy_df = pd.DataFrame(df_rows)
        fetch_jobs(cfg, logger, _scrape_fn=lambda **_kw: jobspy_df)

        # Step 2: rank_jobs
        rank_jobs(cfg, logger, _today=ref_date)

        # Step 3: fetch_staff (mocked StaffSpy)
        staff_rows = []
        for r in golden_staff:
            staff_rows.append({
                "name": r["name"], "headline": r["title"],
                "profile_link": r["profile_url"], "location": r["location"],
                "skills": r["skills"],
                "experiences": [
                    {"company": e["company"], "title": e.get("title"),
                     "date_range": e.get("years", "")}
                    for e in r["experiences"]
                ],
                "educations": [
                    {"school": e["school"], "degree_name": e.get("degree"),
                     "field_of_study": e.get("field"), "date_range": e.get("years")}
                    for e in r["education"]
                ],
                "email": r.get("email"), "is_connection": r.get("contactable", False),
            })
        staff_df = pd.DataFrame(staff_rows)
        mock_session = MagicMock()
        mock_session.scrape_staff.return_value = staff_df
        mock_mod = MagicMock()
        mock_mod.LinkedInSession.return_value = mock_session
        with patch.dict(_sys.modules, {"staffspy": mock_mod}):
            fetch_staff(cfg, ["TechCorp"], logger)

        # Step 4: score_people
        score_people(cfg, logger)

        # Step 5: draft outreach for top person
        people_path = data_dir / "people_to_meet.json"
        if people_path.exists():
            people = _json.loads(people_path.read_text())
            if people:
                impl_draft_outreach(cfg, logger, people[0]["profile_url"])

        return runlog.funnel(cfg.run_log_dir)


# ---------------------------------------------------------------------------
# Chart output (matplotlib if available, text table fallback)
# ---------------------------------------------------------------------------


def _write_funnel_chart(funnel: dict[str, int], out_png: Path) -> str:
    """Write a bar chart to out_png. Returns 'png' or 'text' to indicate what was written."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless
        import matplotlib.pyplot as plt

        labels = list(funnel.keys())
        values = list(funnel.values())
        fig, ax = plt.subplots(figsize=(8, 4))
        bars = ax.barh(labels, values, color="steelblue")
        ax.bar_label(bars, padding=3)
        ax.set_xlabel("Count")
        ax.set_title("Pipeline funnel — golden e2e run")
        ax.invert_yaxis()
        fig.tight_layout()
        out_png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out_png), dpi=120)
        plt.close(fig)
        return "png"
    except ImportError:
        return "text"


def _text_funnel_table(funnel: dict[str, int]) -> str:
    """Render the funnel as a markdown table + ASCII bar chart."""
    max_val = max(funnel.values()) if funnel.values() else 1
    bar_width = 20
    lines = ["| Stage | Count | Bar |", "|---|---|---|"]
    for stage, count in funnel.items():
        filled = round(bar_width * count / max(max_val, 1))
        bar = "█" * filled + "░" * (bar_width - filled)
        lines.append(f"| {stage} | {count} | `{bar}` |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Results markdown writer
# ---------------------------------------------------------------------------


def _write_results_md(
    results: list[ScorerResult],
    funnel: dict[str, int] | None,
    funnel_error: str | None,
    chart_mode: str,
    out_path: Path,
) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n_pass = sum(1 for r in results if r.passed)
    n_total = len(results)
    overall = "ALL PASS" if n_pass == n_total else f"{n_pass}/{n_total} PASS"

    lines: list[str] = [
        "# Evaluation Results — linkedin-coffee-pipeline D6",
        "",
        f"Run at: `{ts}`  |  Python: `{sys.version.split()[0]}`",
        "",
        f"**Overall: {overall}**",
        "",
        "## Per-Capability Scorer Table",
        "",
        "| Capability | Scorer | Pass Bar | Result | Exit | Duration |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        badge = "**PASS**" if r.passed else "**FAIL**"
        lines.append(
            f"| {r.capability} | `{r.description}` | {r.pass_bar}"
            f" | {badge} | {r.exit_code} | {r.duration_s}s |"
        )

    lines += ["", "## Pipeline Funnel (fresh golden e2e run)", ""]
    if funnel_error:
        lines += [f"> **Error running golden e2e**: `{funnel_error}`", ""]
    elif funnel is None:
        lines += ["> Funnel data unavailable.", ""]
    else:
        if chart_mode == "png":
            lines += ["![Funnel](funnel.png)", ""]
        lines += [_text_funnel_table(funnel), ""]

    lines += [
        "## Notes",
        "",
        "- Funnel run uses **golden synthetic data** (`eval/golden/`) in a tmpdir.",
        "  No real LinkedIn scraping or personal data is used.",
        "- `installer-idempotent` runs `./install.sh --dry-run` + `wire_claude_desktop.py --print`.",
        "- `outreach-quality (LLM judge)` rubric is in `eval/outreach_rubric.md`;"
        "  that scorer requires a running LLM and is not automated here.",
        "",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Run all scorers, write results.md + funnel.png, exit 0 iff all pass."""
    print(f"linkedin-coffee-pipeline D6 eval runner")
    print(f"Repo: {REPO}")
    print(f"Running {len(SCORERS)} scorers ...\n")

    results: list[ScorerResult] = []
    for scorer in SCORERS:
        print(f"  [{scorer.capability}] ... ", end="", flush=True)
        result = run_scorer(scorer)
        badge = "PASS" if result.passed else "FAIL"
        print(f"{badge} (exit={result.exit_code}, {result.duration_s}s)")
        results.append(result)

    n_pass = sum(1 for r in results if r.passed)
    n_total = len(results)
    print(f"\nScorers: {n_pass}/{n_total} passed")

    # Fresh golden e2e for funnel evidence
    print("\nRunning fresh golden e2e for funnel evidence ...", flush=True)
    funnel: dict[str, int] | None = None
    funnel_error: str | None = None
    try:
        funnel = _run_golden_funnel()
        print(f"Funnel: {funnel}")
    except Exception as exc:  # noqa: BLE001
        funnel_error = str(exc)
        print(f"Funnel run failed: {exc}")

    # Write chart
    chart_path = EVAL_DIR / "funnel.png"
    chart_mode = "text"
    if funnel is not None:
        chart_mode = _write_funnel_chart(funnel, chart_path)
        if chart_mode == "png":
            print(f"Wrote funnel chart: {chart_path}")
        else:
            print("matplotlib not installed — using text funnel table in results.md")

    # Write results.md
    results_path = EVAL_DIR / "results.md"
    _write_results_md(results, funnel, funnel_error, chart_mode, results_path)
    print(f"\nWrote: {results_path}")

    all_pass = n_pass == n_total
    if all_pass:
        print(f"\nALL {n_total} scorers PASS — D6 complete.")
    else:
        failed = [r.capability for r in results if not r.passed]
        print(f"\n{n_total - n_pass} scorer(s) FAILED: {', '.join(failed)}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
