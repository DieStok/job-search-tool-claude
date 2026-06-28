"""Filesystem layout for the pipeline. All paths derive from the repo root + config."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Repo root = two levels up from this file (src/lcp/paths.py)."""
    return Path(__file__).resolve().parents[2]


# --- cross-platform virtualenv layout ----------------------------------------
# A uv/venv created on POSIX lays out  .venv/bin/<exe>  ; on Windows it is   posix-ok
# .venv\Scripts\<exe>.exe . These helpers are the SINGLE source of truth for
# resolving the venv interpreter / console scripts so no caller hardcodes "bin"
# (which silently breaks on Windows). `os.name == "nt"` is the venv-layout
# discriminator the stdlib venv module itself uses.

def _is_windows() -> bool:
    return os.name == "nt"


def venv_dir(repo: Path | None = None) -> Path:
    return (repo or repo_root()) / ".venv"


def venv_bin_dir(repo: Path | None = None) -> Path:
    """The venv's executables dir: Scripts on Windows, bin on POSIX."""
    return venv_dir(repo) / ("Scripts" if _is_windows() else "bin")


def venv_python(repo: Path | None = None) -> Path:
    """Path to the venv's Python interpreter (python.exe on Windows, python on POSIX)."""
    return venv_bin_dir(repo) / ("python.exe" if _is_windows() else "python")


def venv_script(name: str, repo: Path | None = None) -> Path:
    """Path to a console script installed in the venv (adds .exe on Windows).

    e.g. venv_script("lcp") -> .venv/bin/lcp  (POSIX)  or  .venv\\Scripts\\lcp.exe (Windows).  # posix-ok
    """
    return venv_bin_dir(repo) / (f"{name}.exe" if _is_windows() else name)


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
