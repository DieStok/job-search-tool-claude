"""D1 / AC-001 — config exposes every open question as options + a valid baseline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from lcp.config import ALLOWED, load_config

REPO = Path(__file__).resolve().parents[1]


def test_example_config_loads_and_validates():
    cfg = load_config(REPO / "config" / "config.example.yaml")
    assert cfg.validate() == [], cfg.validate()


def test_options_and_baselines():
    """Every enum knob's baseline is one of its allowed options (the 'options + baseline' shape)."""
    cfg = load_config(REPO / "config" / "config.example.yaml")
    for dotted, allowed in ALLOWED.items():
        val = cfg.get(dotted)
        assert val is not None, f"{dotted} missing a baseline"
        assert val in allowed, f"{dotted}={val} not an allowed option"


def test_compliance_red_lines_present():
    cfg = load_config(REPO / "config" / "config.example.yaml")
    assert cfg.get("compliance.require_human_send") is True
    assert cfg.get("compliance.block_personal_domain_cold_email") is True
    assert isinstance(cfg.get("compliance.max_daily_outreach"), int)


def test_invalid_enum_is_rejected():
    cfg = load_config(REPO / "config" / "config.example.yaml")
    cfg.raw["proxies"]["backend"] = "not_a_backend"
    problems = cfg.validate()
    assert any("proxies.backend" in p for p in problems)


def test_open_questions_checker_passes():
    """The deterministic AC-001 gate exits 0 on the example config."""
    r = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "check_config_covers_open_questions.py"),
         str(REPO / "config" / "config.example.yaml")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
