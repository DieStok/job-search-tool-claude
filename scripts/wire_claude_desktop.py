#!/usr/bin/env python3
"""Merge the linkedin-coffee-pipeline MCP server into claude_desktop_config.json (AC-041).

Safe by construction: backs up first, preserves existing mcpServers, writes valid JSON.
With --print, just prints the entry to paste manually (no file changes).

Usage:
  python scripts/wire_claude_desktop.py --repo /path/to/repo            # merge into the live config
  python scripts/wire_claude_desktop.py --repo /path/to/repo --print    # print the JSON only
  python scripts/wire_claude_desktop.py --repo /path/to/repo --config X # target a specific file (tests)
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

SERVER_KEY = "linkedin-coffee-pipeline"


def default_config_path() -> Path:
    """Claude Desktop's config location per OS."""
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    if sys.platform.startswith("win"):
        import os
        return Path(os.environ.get("APPDATA", "")) / "Claude/claude_desktop_config.json"
    return Path.home() / ".config/Claude/claude_desktop_config.json"


def server_entry(repo: Path) -> dict:
    """The stdio MCP server entry — runs the repo's venv `lcp-mcp`."""
    py = repo / ".venv" / "bin" / "python"
    return {
        "command": str(py),
        "args": ["-m", "lcp.mcp_server"],
        "env": {"LCP_CONFIG": str(repo / "config" / "config.yaml")},
    }


def merge(existing: dict, repo: Path) -> dict:
    """Add/replace ONLY our server key; preserve everything else (AC-041 must-not clobber)."""
    out = dict(existing) if isinstance(existing, dict) else {}
    servers = dict(out.get("mcpServers") or {})
    servers[SERVER_KEY] = server_entry(repo)
    out["mcpServers"] = servers
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--print", dest="print_only", action="store_true")
    args = ap.parse_args(argv)

    repo = args.repo.resolve()
    if args.print_only:
        print(json.dumps({"mcpServers": {SERVER_KEY: server_entry(repo)}}, indent=2))
        return 0

    cfg_path = args.config or default_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    existing: dict = {}
    if cfg_path.exists():
        try:
            existing = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"WARN: {cfg_path} is not valid JSON; refusing to clobber. Use --print and merge by hand.")
            return 1
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = cfg_path.with_suffix(f".json.bak-{stamp}")
        shutil.copy2(cfg_path, backup)
        print(f"backed up existing config -> {backup}")

    merged = merge(existing, repo)
    cfg_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {cfg_path} with server '{SERVER_KEY}'. Restart Claude Desktop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
