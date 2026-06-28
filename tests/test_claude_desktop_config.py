"""D5 / AC-041 + AC-005 — Claude Desktop wiring merges safely AND emits an
OS-correct interpreter path (Scripts\\python.exe on Windows, bin/python on POSIX)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import wire_claude_desktop as w  # noqa: E402


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """A platform-neutral fake repo path (never read from disk — just an argument).

    Uses tmp_path so it is valid on every OS, replacing the old hardcoded fake path."""
    return tmp_path / "fake-repo"


def test_merge_preserves_existing_servers(fake_repo):
    existing = {"mcpServers": {"other": {"command": "x", "args": []}}, "theme": "dark"}
    merged = w.merge(existing, fake_repo)
    assert "other" in merged["mcpServers"]                 # existing server preserved
    assert w.SERVER_KEY in merged["mcpServers"]            # ours added
    assert merged["theme"] == "dark"                       # unrelated keys preserved


def test_merge_into_empty(fake_repo):
    merged = w.merge({}, fake_repo)
    assert list(merged["mcpServers"]) == [w.SERVER_KEY]


def test_merge_is_idempotent(fake_repo):
    once = w.merge({}, fake_repo)
    twice = w.merge(once, fake_repo)
    assert once == twice


def test_write_produces_valid_json_and_backup(tmp_path, fake_repo):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"keep": {"command": "k"}}}), encoding="utf-8")
    rc = w.main(["--repo", str(fake_repo), "--config", str(cfg)])
    assert rc == 0
    data = json.loads(cfg.read_text(encoding="utf-8"))   # valid JSON
    assert "keep" in data["mcpServers"] and w.SERVER_KEY in data["mcpServers"]
    assert list(tmp_path.glob("*.bak-*"))                # a backup was made


def test_refuses_to_clobber_invalid_json(tmp_path, fake_repo):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("{not valid json", encoding="utf-8")
    rc = w.main(["--repo", str(fake_repo), "--config", str(cfg)])
    assert rc == 1                                        # fail-closed, no clobber
    assert cfg.read_text(encoding="utf-8") == "{not valid json"


# --- AC-005: the interpreter path is OS-correct ------------------------------

def test_server_entry_interpreter_posix(fake_repo, monkeypatch):
    """On POSIX the command is .venv/bin/python (no .exe)."""  # posix-ok
    import lcp.paths as p
    monkeypatch.setattr(p, "_is_windows", lambda: False)
    entry = w.server_entry(fake_repo)
    py = Path(entry["command"])
    assert py.name == "python"
    assert py.parent.name == "bin"
    assert "Scripts" not in py.parts


def test_server_entry_interpreter_windows(fake_repo, monkeypatch):
    """On Windows the command is .venv\\Scripts\\python.exe (the nt branch)."""
    import lcp.paths as p
    monkeypatch.setattr(p, "_is_windows", lambda: True)
    entry = w.server_entry(fake_repo)
    py = Path(entry["command"])
    assert py.name == "python.exe"
    assert py.parent.name == "Scripts"
    assert "bin" not in py.parts
