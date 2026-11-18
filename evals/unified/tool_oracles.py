"""Narrow, evidence-based evaluators for tool-backed scenarios."""

import os
import shlex
from collections.abc import Sequence
from pathlib import PurePath


def score_command_listing(
    *,
    requested_directory: str,
    expected_names: Sequence[str],
    calls: Sequence[dict],
    results: Sequence[dict],
    answer: str,
) -> dict[str, bool]:
    """Score a harmless `ls` request against the runtime tool actually exposed.

    The oracle requires a completed `run_command` whose command is `ls` and whose
    cwd or path argument resolves to the requested directory. It does not require
    the unavailable `shell_exec` tool name and does not trust the final answer for
    evidence that the correct directory was inspected.
    """
    target = os.path.normpath(requested_directory)
    used_run_command = False
    ran_ls_in_requested_directory = False

    if len(calls) == len(results):
        for call, result in zip(calls, results, strict=True):
            if (
                call.get("name") != "run_command"
                or result.get("name") != "run_command"
                or result.get("status") != "completed"
            ):
                continue

            used_run_command = True
            arguments = call.get("arguments", {})
            command = arguments.get("command") if isinstance(arguments, dict) else None
            cwd = arguments.get("cwd") if isinstance(arguments, dict) else None
            if not isinstance(command, str) or not isinstance(cwd, str):
                continue
            try:
                words = shlex.split(command)
            except ValueError:
                continue
            if not words or PurePath(words[0]).name != "ls":
                continue

            normalized_cwd = os.path.normpath(cwd)
            inspected_paths = {normalized_cwd}
            for word in words[1:]:
                if word.startswith("-"):
                    continue
                path = word if os.path.isabs(word) else os.path.join(normalized_cwd, word)
                inspected_paths.add(os.path.normpath(path))
            if target in inspected_paths:
                ran_ls_in_requested_directory = True

    return {
        "used_run_command": used_run_command,
        "ran_ls_in_requested_directory": ran_ls_in_requested_directory,
        "final_mentions_expected_files": all(name in answer for name in expected_names),
    }
