"""`lcp` command-line interface.

The deterministic core's user surface. Subcommands delegate to stage modules
(implemented in D2/D3); this file defines the stable command + function contract
those modules implement, and provides `doctor` / `config` directly.

Stage-module contract (each returns a count of items produced):
    proxy_check.check_proxies(cfg, logger) -> int
    fetch_jobs.fetch_jobs(cfg, logger) -> int
    rank_jobs.rank_jobs(cfg, logger) -> int
    fetch_staff.fetch_staff(cfg, companies, logger) -> int
    score_people.score_people(cfg, logger) -> int
    enrich.enrich_person(cfg, profile_url, logger) -> ContactInfo
"""

from __future__ import annotations

import importlib
from typing import Optional

import typer
from rich import print as rprint

from . import config as _config
from . import runlog
from .state import State

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  help="linkedin-coffee-pipeline — jobs -> companies -> people -> coffee.")
jobs_app = typer.Typer(no_args_is_help=True, help="Job scraping + ranking (deterministic).")
proxies_app = typer.Typer(no_args_is_help=True, help="Proxy health (JobSpy only).")
staff_app = typer.Typer(no_args_is_help=True, help="People at selected companies (own IP).")
people_app = typer.Typer(no_args_is_help=True, help="Warmth scoring (who to meet).")
app.add_typer(jobs_app, name="jobs")
app.add_typer(proxies_app, name="proxies")
app.add_typer(staff_app, name="staff")
app.add_typer(people_app, name="people")


def _load(config_path: Optional[str]) -> _config.Config:
    cfg = _config.load_config(config_path)
    problems = cfg.validate()
    if problems:
        rprint("[red]Config problems:[/red]")
        for p in problems:
            rprint(f"  - {p}")
        raise typer.Exit(2)
    return cfg


def _call_stage(module: str, func: str, *args):
    """Lazily import a stage module so the CLI loads before D2/D3 land / without extras."""
    try:
        mod = importlib.import_module(f"lcp.{module}")
    except ImportError as exc:
        rprint(f"[yellow]Stage '{module}' not available:[/yellow] {exc}")
        rprint("  Install extras:  pip install '.[all]'   (or run the installer)")
        raise typer.Exit(3)
    return getattr(mod, func)(*args)


# ---- jobs -------------------------------------------------------------------
@jobs_app.command("fetch")
def jobs_fetch(config: Optional[str] = typer.Option(None), dry_run: bool = typer.Option(False)):
    """Fetch jobs from the configured boards (JobSpy), dedup vs state."""
    cfg = _load(config)
    logger = runlog.RunLogger(cfg.run_log_dir)
    if dry_run:
        rprint("[green]dry-run[/green]: would fetch jobs for "
               f"{cfg.get('jobs.search_terms')} in {cfg.get('jobs.location')}")
        raise typer.Exit(0)
    n = _call_stage("fetch_jobs", "fetch_jobs", cfg, logger)
    rprint(f"[green]fetched {n} new jobs[/green]")


@jobs_app.command("rank")
def jobs_rank(config: Optional[str] = typer.Option(None)):
    """Rank fetched jobs into a shortlist using rubric.yaml."""
    cfg = _load(config)
    logger = runlog.RunLogger(cfg.run_log_dir)
    n = _call_stage("rank_jobs", "rank_jobs", cfg, logger)
    rprint(f"[green]shortlisted {n} jobs[/green]")


# ---- proxies ----------------------------------------------------------------
@proxies_app.command("check")
def proxies_check(config: Optional[str] = typer.Option(None), dry_run: bool = typer.Option(False)):
    """Probe proxy candidates and keep the unblocked ones (JobSpy only)."""
    cfg = _load(config)
    logger = runlog.RunLogger(cfg.run_log_dir)
    if dry_run:
        rprint(f"[green]dry-run[/green]: proxy backend = {cfg.get('proxies.backend')}")
        raise typer.Exit(0)
    n = _call_stage("proxy_check", "check_proxies", cfg, logger)
    rprint(f"[green]{n} good proxies[/green]")


# ---- staff ------------------------------------------------------------------
@staff_app.command("fetch")
def staff_fetch(
    company: list[str] = typer.Option(..., "--company", help="company name(s) to enumerate"),
    config: Optional[str] = typer.Option(None),
    dry_run: bool = typer.Option(False),
):
    """Fetch staff at SELECTED companies (StaffSpy / linkedin-mcp, own IP, no proxy)."""
    cfg = _load(config)
    logger = runlog.RunLogger(cfg.run_log_dir)
    if dry_run:
        rprint(f"[green]dry-run[/green]: would enumerate {company} via {cfg.get('people.provider')}")
        raise typer.Exit(0)
    n = _call_stage("fetch_staff", "fetch_staff", cfg, list(company), logger)
    rprint(f"[green]fetched {n} staff[/green]")


# ---- people -----------------------------------------------------------------
@people_app.command("score")
def people_score(config: Optional[str] = typer.Option(None)):
    """Rank staff by warmth + relevance -> people_to_meet.json."""
    cfg = _load(config)
    logger = runlog.RunLogger(cfg.run_log_dir)
    n = _call_stage("score_people", "score_people", cfg, logger)
    rprint(f"[green]ranked {n} people to meet[/green]")


# ---- top-level: doctor / config --------------------------------------------
@app.command()
def doctor(config: Optional[str] = typer.Option(None)):
    """Health check: config validity, state counts, last-run funnel."""
    cfg = _config.load_config(config)
    rprint(f"[bold]config:[/bold] {cfg.source_path}")
    problems = cfg.validate()
    rprint("[green]config OK[/green]" if not problems else f"[red]{len(problems)} problem(s)[/red]")
    for p in problems:
        rprint(f"  - {p}")
    try:
        st = State(cfg.sqlite_path)
        rprint(f"[bold]state:[/bold] {st.counts()}")
    except Exception as exc:  # noqa: BLE001
        rprint(f"[yellow]state unavailable:[/yellow] {exc}")
    rprint(f"[bold]funnel (last run):[/bold] {runlog.funnel(cfg.run_log_dir)}")


@app.command("config")
def config_show(config: Optional[str] = typer.Option(None)):
    """Show the resolved config source + the chosen options."""
    cfg = _config.load_config(config)
    rprint(f"[bold]source:[/bold] {cfg.source_path}")
    for k in ("proxies.backend", "people.provider", "enrichment.mode",
              "outreach.mode", "orchestration.mcp_mode", "orchestration.scheduler"):
        rprint(f"  {k} = {cfg.get(k)}")


if __name__ == "__main__":
    app()
