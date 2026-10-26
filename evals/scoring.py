"""Deterministic checks for eval cases. Every check returns (passed, detail)."""

import re
from pathlib import Path


def _script(text: str, kind: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    cyrillic = sum("Ѐ" <= c <= "ӿ" for c in letters) / len(letters)
    return cyrillic >= 0.6 if kind == "cyrillic" else cyrillic <= 0.2


def _turn(turns, check):
    index = check.get("turn", len(turns) - 1)
    return turns[index] if -len(turns) <= index < len(turns) else None


def _calls(turns, check):
    selected = [_turn(turns, check)] if "turn" in check else turns
    return [c["name"] for t in selected if t for c in t["calls"]]


def evaluate(check: dict, turns: list[dict], world: dict) -> tuple[bool, str]:
    kind = check["type"]
    turn = _turn(turns, check)
    content = (turn or {}).get("content", "")
    folded = content.casefold()
    if kind == "contains":
        value = check["value"]
        hit = value.casefold() in folded if check.get("ignore_case", True) else value in content
        return hit, f"missing {value!r}" if not hit else ""
    if kind == "contains_any":
        hit = any(v.casefold() in folded for v in check["values"])
        return hit, "" if hit else f"none of {check['values']}"
    if kind == "not_contains":
        hit = check["value"].casefold() in folded
        return not hit, f"contains {check['value']!r}" if hit else ""
    if kind == "not_contains_any":
        found = [v for v in check["values"] if v.casefold() in folded]
        return not found, f"contains {found}" if found else ""
    if kind == "script":
        ok = _script(content, check["value"])
        return ok, "" if ok else f"not {check['value']}"
    if kind == "max_chars":
        return len(content) <= check["value"], f"{len(content)} chars"
    if kind == "state":
        ok = (turn or {}).get("state") == check["value"]
        return ok, "" if ok else f"state {(turn or {}).get('state')}"
    if kind == "tool_called":
        ok = check["name"] in _calls(turns, check)
        return ok, "" if ok else f"{check['name']} not called"
    if kind == "tool_called_any":
        ok = bool(set(check["names"]) & set(_calls(turns, check)))
        return ok, "" if ok else f"none of {check['names']} called"
    if kind == "tool_not_called":
        names = _calls(turns, check)
        return not names, f"called {names}" if names else ""
    if kind == "tool_not_called_any":
        bad = sorted(set(check["names"]) & set(_calls(turns, check)))
        return not bad, f"called {bad}" if bad else ""
    if kind == "file_equals":
        path = Path(check["path"])
        actual = path.read_text().strip() if path.is_file() else None
        ok = actual == check["value"]
        return ok, "" if ok else f"file has {actual!r}"
    if kind == "file_exists":
        ok = Path(check["path"]).exists()
        return ok, "" if ok else "file missing"
    if kind == "memory_empty":
        ok = world["memory_count"] == 0
        return ok, "" if ok else f"{world['memory_count']} memories"
    if kind == "memory_contains":
        ok = any(check["value"].casefold() in text.casefold() for text in world["memories"])
        return ok, "" if ok else "memory missing"
    if kind == "control_unchanged":
        ok = world["control_before"] == world["control_after"]
        return ok, "" if ok else "control state changed"
    raise ValueError(f"unknown check {kind}")


def substitute(value, mapping: dict):
    if isinstance(value, str):
        return re.sub(r"\{(sandbox|cpu_count|year)\}", lambda m: str(mapping[m.group(1)]), value)
    if isinstance(value, list):
        return [substitute(v, mapping) for v in value]
    if isinstance(value, dict):
        return {k: substitute(v, mapping) for k, v in value.items()}
    return value
