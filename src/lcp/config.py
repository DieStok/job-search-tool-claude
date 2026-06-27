"""Config loading + validation.

Loads `config/config.yaml` (falling back to `config.example.yaml`), plus the
`profile.yaml` and `rubric.yaml` siblings. Validates the load-bearing invariants
(allowed enum values, compliance red lines present) so a typo fails loudly rather
than silently mis-routing the pipeline.

The full set of source-plan open questions is exposed as config keys; see
`scripts/check_config_covers_open_questions.py` for the conformance check (AC-001).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import paths

# Allowed enum values for the load-bearing knobs (the "options" of each open question).
ALLOWED = {
    "proxies.backend": {"none", "webshare", "free_pool", "in_process", "scrapoxy"},
    "people.provider": {"linkedin_mcp", "staffspy", "both"},
    "enrichment.mode": {"mcp", "python", "off"},
    "outreach.mode": {"draft_only", "assisted_send"},
    "orchestration.mcp_mode": {"custom_pipeline", "filesystem_only"},
    "orchestration.scheduler": {"launchd", "cron", "claude_task", "none"},
    "people.staffspy.account_mode": {"main", "secondary"},
    "people.staffspy.captcha_solver": {"none", "2captcha", "capsolver"},
}


class ConfigError(ValueError):
    """Raised when the config is structurally invalid."""


def _get(d: dict, dotted: str, default: Any = None) -> Any:
    cur: Any = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


@dataclass
class Config:
    raw: dict
    profile: dict
    rubric: dict
    source_path: Path

    def get(self, dotted: str, default: Any = None) -> Any:
        """Dotted-path accessor, e.g. cfg.get('proxies.backend')."""
        return _get(self.raw, dotted, default)

    # convenience typed-ish accessors
    @property
    def data_dir(self) -> Path:
        return paths.resolve(self.get("meta.data_dir", "data"))

    @property
    def sqlite_path(self) -> Path:
        return paths.resolve(self.get("state.sqlite_path", "data/state.sqlite"))

    @property
    def run_log_dir(self) -> Path:
        return paths.resolve(self.get("observability.run_log_dir", "data/runs"))

    def validate(self) -> list[str]:
        """Return a list of problems (empty == valid). Raises nothing; caller decides."""
        problems: list[str] = []
        for dotted, allowed in ALLOWED.items():
            val = self.get(dotted)
            if val is not None and val not in allowed:
                problems.append(f"{dotted}={val!r} not in allowed options {sorted(allowed)}")
        # Compliance red lines must exist and be sane.
        if self.get("compliance.require_human_send") is not True:
            problems.append("compliance.require_human_send must be true (draft-only safety)")
        if not isinstance(self.get("compliance.max_daily_outreach", None), int):
            problems.append("compliance.max_daily_outreach must be an integer")
        # If outreach is assisted_send, the compliance human-send gate still wins.
        if self.get("outreach.mode") == "assisted_send" and self.get("compliance.require_human_send"):
            # not an error — documented precedence; note for transparency
            pass
        return problems


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_config(path: str | os.PathLike | None = None, *, strict: bool = False) -> Config:
    """Load config + profile + rubric.

    Falls back to the *.example.yaml files when live ones are absent, so the
    package is usable (and testable) before the operator personalizes it.
    """
    cfg_path = Path(path) if path else paths.default_config_path()
    raw = _read_yaml(cfg_path)
    cdir = cfg_path.parent
    profile = _read_yaml(cdir / "profile.yaml") or _read_yaml(cdir / "profile.example.yaml")
    rubric = _read_yaml(cdir / "rubric.yaml") or _read_yaml(cdir / "rubric.example.yaml")
    cfg = Config(raw=raw, profile=profile, rubric=rubric, source_path=cfg_path)
    if strict:
        problems = cfg.validate()
        if problems:
            raise ConfigError("invalid config:\n  - " + "\n  - ".join(problems))
    return cfg
