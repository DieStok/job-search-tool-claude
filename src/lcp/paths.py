"""Filesystem layout for the pipeline. All paths derive from the repo root + config."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Repo root = two levels up from this file (src/lcp/paths.py)."""
    return Path(__file__).resolve().parents[2]


def resolve(path_like: str | os.PathLike, base: Path | None = None) -> Path:
    """Resolve a possibly-relative path against the repo root (or a given base)."""
    p = Path(path_like)
    if p.is_absolute():
        return p
    return (base or repo_root()) / p


def config_dir() -> Path:
    return repo_root() / "config"


def default_config_path() -> Path:
    """Live config if present, else the committed example (lets tests run unconfigured)."""
    live = config_dir() / "config.yaml"
    return live if live.exists() else config_dir() / "config.example.yaml"
