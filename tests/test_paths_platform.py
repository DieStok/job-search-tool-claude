"""AC-003 — the venv interpreter / console-script resolvers in lcp.paths pick the
OS-correct layout: Scripts\\<exe>.exe on Windows, bin/<exe> on POSIX.

These run on any host because the OS branch is driven by a single overridable
predicate (`lcp.paths._is_windows`), which we monkeypatch to exercise BOTH layouts
regardless of the machine the test runs on (so the Windows branch is covered on a Mac
CI, and the POSIX branch is covered on a Windows CI)."""

from __future__ import annotations

from pathlib import Path

import pytest

import lcp.paths as p


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return tmp_path / "repo"


def test_posix_layout(repo, monkeypatch):
    monkeypatch.setattr(p, "_is_windows", lambda: False)
    assert p.venv_bin_dir(repo).name == "bin"
    py = p.venv_python(repo)
    assert py.name == "python"
    assert py.parent.name == "bin"
    lcp = p.venv_script("lcp", repo)
    assert lcp.name == "lcp"                 # no .exe on POSIX
    assert lcp.parent.name == "bin"


def test_windows_layout(repo, monkeypatch):
    monkeypatch.setattr(p, "_is_windows", lambda: True)
    assert p.venv_bin_dir(repo).name == "Scripts"
    py = p.venv_python(repo)
    assert py.name == "python.exe"
    assert py.parent.name == "Scripts"
    lcp = p.venv_script("lcp", repo)
    assert lcp.name == "lcp.exe"             # .exe appended on Windows
    assert lcp.parent.name == "Scripts"


def test_is_windows_tracks_os_name(monkeypatch):
    """The discriminator follows os.name, matching the stdlib venv module's own rule."""
    import os
    monkeypatch.setattr(os, "name", "nt")
    assert p._is_windows() is True
    monkeypatch.setattr(os, "name", "posix")
    assert p._is_windows() is False


def test_defaults_to_repo_root_when_none():
    """Called with no repo arg, helpers anchor at the real repo root (smoke)."""
    assert p.venv_python().parent.parent == p.repo_root() / ".venv"
