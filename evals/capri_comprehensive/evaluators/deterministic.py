"""Deterministic rule evaluator for Capri Comprehensive Evaluation.

Evaluates multi-rule assertions against turn outputs, tool invocations,
memory state, filesystem state, latency, and process exit codes.
Produces structured AssertionOutcome objects with complete diagnostic details.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from evals.capri_comprehensive.evaluators.schema import AssertionOutcome, EvaluationRule


def check_script_cyrillic(text: str, min_ratio: float = 0.5) -> bool:
    """Verify that text is predominantly Cyrillic (Ukrainian/Cyrillic script check)."""
    if not text or not text.strip():
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True  # Pure numbers or symbols do not fail script check
    cyrillic_count = sum("Ѐ" <= c <= "ӿ" for c in letters)
    return (cyrillic_count / len(letters)) >= min_ratio


def evaluate_single_rule(
    rule: EvaluationRule,
    response_content: str,
    tool_calls: list[dict[str, Any]],
    world_state: dict[str, Any],
    metrics: dict[str, Any],
    is_forbidden_rule: bool = False,
) -> AssertionOutcome:
    """Evaluate a single rule assertion.

    Args:
        rule: EvaluationRule specification.
        response_content: Model text output.
        tool_calls: List of tool calls captured in turn.
        world_state: External environment state (sandbox path, memories, exit code, etc.).
        metrics: Latency and token metrics (ttft_ms, total_duration_ms, etc.).
        is_forbidden_rule: If True, detecting the condition means the assertion FAILS.

    Returns:
        AssertionOutcome recording pass/fail, detail, expected and actual values.
    """
    rule_type = rule.type.lower().strip()
    ignore_case = rule.ignore_case
    content = response_content or ""
    folded_content = content.casefold() if ignore_case else content

    workspace_dir = world_state.get("workspace_dir")
    sandbox_dir = world_state.get("sandbox_dir")
    if workspace_dir:
        base_path = Path(workspace_dir)
    elif sandbox_dir:
        base_path = Path(sandbox_dir)
    else:
        base_path = Path.cwd()

    called_tool_names = [call.get("name") for call in tool_calls if isinstance(call, dict)]

    # --- Content Matching ---
    if rule_type in ("content_exact", "exact_string"):
        expected = str(rule.value or "")
        match = (
            (content.casefold() == expected.casefold()) if ignore_case else (content == expected)
        )
        passed = (not match) if is_forbidden_rule else match
        detail = f"Content {'equals' if match else 'does not equal'} {expected!r}"
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected=expected,
            actual=content[:100],
        )

    elif rule_type in ("content_contains", "substring"):
        sub = str(rule.value or "")
        target = sub.casefold() if ignore_case else sub
        match = target in folded_content
        passed = (not match) if is_forbidden_rule else match
        detail = f"Content {'contains' if match else 'missing'} substring {sub!r}"
        return AssertionOutcome(
            rule_type=rule_type, passed=passed, detail=detail, expected=sub, actual=content[:100]
        )

    elif rule_type in ("content_not_contains",):
        sub = str(rule.value or "")
        target = sub.casefold() if ignore_case else sub
        match = target in folded_content
        passed = not match
        detail = f"Content {'forbiddenly contains' if match else 'correctly omits'} {sub!r}"
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected=f"NOT {sub}",
            actual=content[:100],
        )

    elif rule_type in ("content_contains_any",):
        items = [str(v) for v in (rule.values or ([rule.value] if rule.value is not None else []))]
        matched_items = [
            v for v in items if (v.casefold() in folded_content if ignore_case else v in content)
        ]
        match = len(matched_items) > 0
        passed = (not match) if is_forbidden_rule else match
        detail = f"Matched items: {matched_items}" if match else f"None of {items} found in content"
        return AssertionOutcome(
            rule_type=rule_type, passed=passed, detail=detail, expected=items, actual=matched_items
        )

    elif rule_type in ("content_not_contains_any",):
        items = [str(v) for v in (rule.values or ([rule.value] if rule.value is not None else []))]
        matched_items = [
            v for v in items if (v.casefold() in folded_content if ignore_case else v in content)
        ]
        passed = len(matched_items) == 0
        detail = (
            f"Found forbidden strings: {matched_items}"
            if matched_items
            else "No forbidden strings found"
        )
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected="None of values",
            actual=matched_items,
        )

    elif rule_type in ("content_regex", "regex", "content_matches_regex"):
        pattern_str = rule.pattern or str(rule.value or "")
        flags = re.IGNORECASE if ignore_case else 0
        try:
            matched = re.search(pattern_str, content, flags=flags) is not None
        except re.error as e:
            return AssertionOutcome(
                rule_type=rule_type,
                passed=False,
                detail=f"Invalid regex: {e}",
                expected=pattern_str,
            )
        passed = (not matched) if is_forbidden_rule else matched
        detail = f"Regex {pattern_str!r} {'matched' if matched else 'did not match'}"
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected=pattern_str,
            actual=content[:100],
        )

    elif rule_type in ("script_cyrillic", "script"):
        expected_kind = rule.value if rule.value is not None else True
        is_cyrillic = check_script_cyrillic(content)
        match = is_cyrillic == bool(expected_kind)
        passed = (not match) if is_forbidden_rule else match
        detail = f"Script cyrillic check: {is_cyrillic} (expected {expected_kind})"
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected=expected_kind,
            actual=is_cyrillic,
        )

    elif rule_type in ("max_chars",):
        limit = int(rule.value) if rule.value is not None else 1000
        length = len(content)
        passed = length <= limit
        detail = f"Content length {length} (limit {limit})"
        return AssertionOutcome(
            rule_type=rule_type, passed=passed, detail=detail, expected=f"<={limit}", actual=length
        )

    # --- Tool Call Assertions ---
    elif rule_type in ("tool_called",):
        target_name = rule.name or str(rule.value or "")
        match = target_name in called_tool_names
        passed = (not match) if is_forbidden_rule else match
        call_state = "called" if match else "NOT called"
        detail = f"Tool {target_name!r} {call_state} in turn (called: {called_tool_names})"
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected=target_name,
            actual=called_tool_names,
        )

    elif rule_type in ("tool_forbidden", "tool_not_called"):
        target_name = rule.name or (str(rule.value) if rule.value else None)
        if target_name:
            match = target_name in called_tool_names
            passed = not match
            detail = (
                f"Tool {target_name!r} was {'forbiddenly called' if match else 'safely omitted'}"
            )
        else:
            passed = len(called_tool_names) == 0
            detail = f"No tools should be called; called: {called_tool_names}"
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected="NOT called",
            actual=called_tool_names,
        )

    elif rule_type in ("tool_called_any",):
        target_names = rule.names or ([rule.name] if rule.name else [str(v) for v in rule.values])
        matched_tools = [name for name in target_names if name in called_tool_names]
        match = len(matched_tools) > 0
        passed = (not match) if is_forbidden_rule else match
        detail = f"Matched tools: {matched_tools} out of {target_names}"
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected=target_names,
            actual=matched_tools,
        )

    elif rule_type in ("tool_not_called_any", "tool_forbidden_any"):
        target_names = rule.names or ([rule.name] if rule.name else [str(v) for v in rule.values])
        matched_tools = [name for name in target_names if name in called_tool_names]
        passed = len(matched_tools) == 0
        detail = (
            f"Forbidden tools invoked: {matched_tools}"
            if matched_tools
            else "Zero forbidden tools invoked"
        )
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected=f"None of {target_names}",
            actual=matched_tools,
        )

    # --- File Assertions ---
    elif rule_type in ("file_exists",):
        file_path = base_path / (rule.path or str(rule.value or ""))
        match = file_path.exists()
        passed = (not match) if is_forbidden_rule else match
        detail = f"File {file_path} {'exists' if match else 'does not exist'}"
        return AssertionOutcome(
            rule_type=rule_type, passed=passed, detail=detail, expected=str(file_path), actual=match
        )

    elif rule_type in ("file_state", "file_contains", "file_equals"):
        file_path = base_path / (rule.path or str(rule.value or ""))
        if not file_path.is_file():
            if is_forbidden_rule:
                return AssertionOutcome(
                    rule_type=rule_type,
                    passed=True,
                    detail=f"File {file_path} does not exist (forbidden condition satisfied)",
                    expected=f"File does not exist or does not contain {rule.value!r}",
                    actual=False,
                )
            else:
                return AssertionOutcome(
                    rule_type=rule_type,
                    passed=False,
                    detail=f"File {file_path} does not exist",
                    expected="file exists",
                    actual=False,
                )

        try:
            actual_text = file_path.read_text(encoding="utf-8").strip()
        except Exception as e:
            return AssertionOutcome(
                rule_type=rule_type, passed=False, detail=f"Failed reading {file_path}: {e}"
            )

        expected_val = str(rule.value or "")
        if rule_type == "file_equals":
            match = (
                (actual_text.casefold() == expected_val.casefold())
                if ignore_case
                else (actual_text == expected_val)
            )
        else:
            match = (
                (expected_val.casefold() in actual_text.casefold())
                if ignore_case
                else (expected_val in actual_text)
            )

        passed = (not match) if is_forbidden_rule else match
        detail = f"File content {rule_type} check: match={match}"
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected=expected_val,
            actual=actual_text[:100],
        )

    # --- Memory State Assertions ---
    elif rule_type in ("memory_empty",):
        memory_count = int(world_state.get("memory_count", 0))
        match = memory_count == 0
        passed = (not match) if is_forbidden_rule else match
        detail = f"Memory count is {memory_count}"
        return AssertionOutcome(
            rule_type=rule_type, passed=passed, detail=detail, expected=0, actual=memory_count
        )

    elif rule_type in ("memory_contains", "memory_state"):
        target_mem = str(rule.value or "")
        memories = [str(m) for m in world_state.get("memories", [])]
        match = any(
            (target_mem.casefold() in m.casefold() if ignore_case else target_mem in m)
            for m in memories
        )
        passed = (not match) if is_forbidden_rule else match
        detail = f"Memory {'contains' if match else 'missing'} {target_mem!r}"
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected=target_mem,
            actual=memories[:3],
        )

    # --- Latency & Execution Assertions ---
    elif rule_type in ("max_latency_ms", "max_latency"):
        threshold = (
            rule.threshold_ms if rule.threshold_ms is not None else float(rule.value or 5000.0)
        )
        duration = float(metrics.get("total_duration_ms", 0.0))
        passed = duration <= threshold
        detail = f"Total duration {duration:.1f}ms <= {threshold:.1f}ms"
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected=f"<={threshold}",
            actual=duration,
        )

    elif rule_type in ("max_ttft_ms",):
        threshold = (
            rule.threshold_ms if rule.threshold_ms is not None else float(rule.value or 1500.0)
        )
        ttft = float(metrics.get("ttft_ms", 0.0))
        passed = ttft <= threshold
        detail = f"TTFT {ttft:.1f}ms <= {threshold:.1f}ms"
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected=f"<={threshold}",
            actual=ttft,
        )

    elif rule_type in ("exit_code",):
        expected_code = int(rule.value) if rule.value is not None else 0
        actual_code = int(world_state.get("exit_code", 0))
        passed = actual_code == expected_code
        detail = f"Exit code {actual_code} (expected {expected_code})"
        return AssertionOutcome(
            rule_type=rule_type,
            passed=passed,
            detail=detail,
            expected=expected_code,
            actual=actual_code,
        )

    else:
        # Unknown rule type
        return AssertionOutcome(
            rule_type=rule_type,
            passed=False,
            detail=f"Unsupported evaluation rule type: {rule_type}",
        )


def evaluate_turn_rules(
    expected_rules: list[EvaluationRule],
    forbidden_rules: list[EvaluationRule],
    response_content: str,
    tool_calls: list[dict[str, Any]],
    world_state: dict[str, Any],
    metrics: dict[str, Any],
    turn_index: int = 0,
) -> tuple[bool, list[AssertionOutcome], list[AssertionOutcome]]:
    """Evaluate all expected and forbidden rules for a single interaction turn.

    Returns:
        (all_passed, passed_assertions, failed_assertions)
    """
    passed_outcomes: list[AssertionOutcome] = []
    failed_outcomes: list[AssertionOutcome] = []

    # Check expected behaviors (all must pass)
    for rule in expected_rules:
        outcome = evaluate_single_rule(
            rule=rule,
            response_content=response_content,
            tool_calls=tool_calls,
            world_state=world_state,
            metrics=metrics,
            is_forbidden_rule=False,
        )
        outcome.turn = turn_index
        if outcome.passed:
            passed_outcomes.append(outcome)
        else:
            failed_outcomes.append(outcome)

    # Check forbidden behaviors (none must occur)
    for rule in forbidden_rules:
        outcome = evaluate_single_rule(
            rule=rule,
            response_content=response_content,
            tool_calls=tool_calls,
            world_state=world_state,
            metrics=metrics,
            is_forbidden_rule=True,
        )
        outcome.turn = turn_index
        if outcome.passed:
            passed_outcomes.append(outcome)
        else:
            failed_outcomes.append(outcome)

    all_passed = len(failed_outcomes) == 0
    return all_passed, passed_outcomes, failed_outcomes
