#!/usr/bin/env python3
"""Scratch launcher for evals.subscription_bridge that cleanly disables Codex native tools/plugins.

Avoids touching pinned .worktrees/eval-run (d116105) while preventing Codex CLI from firing
native web_search / command_execution / user MCP plugins instead of returning runtime tool_calls.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

EVAL_REPO = Path(os.environ.get("B12_EVAL_REPO", Path.home() / "Projects/B-12/.worktrees/eval-run"))
if str(EVAL_REPO) not in sys.path:
    sys.path.insert(0, str(EVAL_REPO))

import evals.subscription_bridge as sb  # noqa: E402


def _clean_codex_overrides(_config_path=None):
    return [
        "--ignore-user-config",
        "--ignore-rules",
        "-c",
        'web_search="disabled"',
        "--disable",
        "apps",
        "--disable",
        "browser_use",
        "--disable",
        "browser_use_external",
        "--disable",
        "in_app_browser",
        "--disable",
        "shell_tool",
        "--disable",
        "unified_exec",
    ]


sb.codex_overrides = _clean_codex_overrides

if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    sb.main()
