"""Test tool definitions generation across modes."""

import copy
from typing import Any

STANDARD_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Пошук спогадів, фактів та автобіографічних записів у базі довготривалої пам'яті B-12 за семантичним запитом.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Пошуковий семантичний запит для пошуку в пам'яті",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Максимальна кількість результатів для повернення",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Прочитати вміст файлу за вказаним шляхом у робочій директорії пісочниці.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Шлях до файлу для читання",
                    },
                },
                "required": ["path"],
            },
        },
    },
]


def get_tool_definitions(mode: str = "FULL") -> list[dict[str, Any]]:
    mode_upper = mode.upper().strip()
    if mode_upper in ("OFF", "NONE", "DISABLED"):
        return []

    if mode_upper == "FULL":
        return copy.deepcopy(STANDARD_TOOLS)

    if mode_upper == "STRICT":
        strict_tools = []
        for t in STANDARD_TOOLS:
            fn = t["function"]
            props = fn.get("parameters", {}).get("properties", {})
            strict_props = {
                k: {"type": v.get("type", "string")}
                for k, v in props.items()
            }
            strict_tools.append({
                "type": "function",
                "function": {
                    "name": fn["name"],
                    "description": fn["name"],
                    "parameters": {
                        "type": "object",
                        "properties": strict_props,
                        "required": fn.get("parameters", {}).get("required", []),
                    },
                },
            })
        return strict_tools

    if mode_upper == "MINIMAL":
        minimal_tools = []
        for t in STANDARD_TOOLS:
            fn = t["function"]
            minimal_tools.append({
                "type": "function",
                "function": {
                    "name": fn["name"],
                    "description": fn["name"],
                    "parameters": {
                        "type": "object",
                        "properties": {},
                    },
                },
            })
        return minimal_tools

    return copy.deepcopy(STANDARD_TOOLS)


full_tools = get_tool_definitions("FULL")
assert len(full_tools) == 2
assert "Пошук спогадів" in full_tools[0]["function"]["description"]
assert "description" in full_tools[0]["function"]["parameters"]["properties"]["query"]

strict_tools = get_tool_definitions("STRICT")
assert len(strict_tools) == 2
assert strict_tools[0]["function"]["description"] == "memory_search"
assert "description" not in strict_tools[0]["function"]["parameters"]["properties"]["query"]
assert strict_tools[0]["function"]["parameters"]["properties"]["query"]["type"] == "string"

min_tools = get_tool_definitions("MINIMAL")
assert len(min_tools) == 2
assert min_tools[0]["function"]["description"] == "memory_search"
assert min_tools[0]["function"]["parameters"]["properties"] == {}

off_tools = get_tool_definitions("OFF")
assert off_tools == []

print("Tool definitions tested across all modes successfully!")
