"""D5 / AC-041 — Claude Desktop wiring merges safely (preserves existing, valid JSON)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import wire_claude_desktop as w  # noqa: E402

REPO = Path("/tmp/fake-repo")


def test_merge_preserves_existing_servers():
    existing = {"mcpServers": {"other": {"command": "x", "args": []}}, "theme": "dark"}
    merged = w.merge(existing, REPO)
    assert "other" in merged["mcpServers"]                 # existing server preserved
    assert w.SERVER_KEY in merged["mcpServers"]            # ours added
    assert merged["theme"] == "dark"                       # unrelated keys preserved


def test_merge_into_empty():
    merged = w.merge({}, REPO)
    assert list(merged["mcpServers"]) == [w.SERVER_KEY]


def test_merge_is_idempotent():
    once = w.merge({}, REPO)
    twice = w.merge(once, REPO)
    assert once == twice


def test_write_produces_valid_json_and_backup(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"keep": {"command": "k"}}}), encoding="utf-8")
    rc = w.main(["--repo", str(REPO), "--config", str(cfg)])
    assert rc == 0
    data = json.loads(cfg.read_text(encoding="utf-8"))   # valid JSON
    assert "keep" in data["mcpServers"] and w.SERVER_KEY in data["mcpServers"]
    assert list(tmp_path.glob("*.bak-*"))                # a backup was made


def test_refuses_to_clobber_invalid_json(tmp_path):
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text("{not valid json", encoding="utf-8")
    rc = w.main(["--repo", str(REPO), "--config", str(cfg)])
    assert rc == 1                                        # fail-closed, no clobber
    assert cfg.read_text(encoding="utf-8") == "{not valid json"
