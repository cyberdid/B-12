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

# intg-live-v1 C61 on gpt-6-luna (23.11.2026): the model read the Codex CLI's own environment
# (read-only sandbox, writable root under /home, shell disabled) as limits of the runtime and
# answered "no file tools" although file_read/file_list/run_command were offered.
sb.PREAMBLE = sb.PREAMBLE + (
    " The CLI hosting you may describe its own working directory, sandbox, writable roots or "
    "disabled shell: that describes only the host, never the runtime. Paths such as /sandbox/... "
    "belong to the runtime and are reachable only through the runtime tools listed below. When a "
    "listed tool fits the task, call it through tool_calls; never say a listed tool is "
    "unavailable."
)

_REQUEST_LOG = (
    Path(os.environ.get("B12_BRIDGE_REQUEST_LOG", ""))
    if os.environ.get("B12_BRIDGE_REQUEST_LOG")
    else None
)
_ask_backend = sb.ask_backend


async def _logged_ask_backend(backend, model, body, **kwargs):
    """Record offered tools and the structured answer of every round (the bridge's own log is
    in memory only)."""
    structured, usage = await _ask_backend(backend, model, body, **kwargs)
    if _REQUEST_LOG is not None:
        import json

        entry = {
            "offered_tools": sorted(
                (t.get("function") or {}).get("name", "?") for t in body.get("tools", [])
            ),
            "answer": structured,
        }
        with _REQUEST_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return structured, usage


sb.ask_backend = _logged_ask_backend

if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    sb.main()
