"""Experimental pytest instrumentation; never imported by production B-12."""
from collections import Counter
from pathlib import Path
import hashlib
import json
import os

import pytest


@pytest.fixture(autouse=True)
def measure_request_sizes(scripted_ollama, monkeypatch):
    import b12.agent as agent_module
    from b12.model_profile import ModelProfile

    state, settings = scripted_ollama
    profile = ModelProfile(settings)
    prefix = agent_module.CAPRI_PERSONA_PROMPT
    original = agent_module.SYSTEM_PROMPT
    assert original.startswith(prefix)
    arm = os.environ["CAPRI_PROBE_ARM"]
    committed = json.loads((Path(__file__).parent / "head-persona.json").read_text())
    replacements = {1: "a", 2: "я", 3: "—", 4: "😀"}
    neutral = "".join(replacements[len(char.encode("utf-8"))] for char in prefix)
    prefixes = {"current": prefix, "head": committed, "removed": "", "neutral": neutral}
    chosen = prefixes[arm] + original[len(prefix):]
    init = agent_module.Agent.__init__

    def initialize(self, *arguments, **options):
        assert "system_prompt" not in options
        options["system_prompt"] = chosen
        return init(self, *arguments, **options)

    monkeypatch.setattr(agent_module.Agent, "__init__", initialize)
    try:
        yield
    finally:
        requests = []
        for index, request in enumerate(state["requests"]):
            roles = Counter()
            for message in request["messages"]:
                roles[message["role"]] += len(message.get("content") or "")
            requests.append({
                "round": index + 1, "total_message_chars": sum(roles.values()),
                "message_chars_by_role": dict(roles),
                "synthetic_tokens_with_tools": profile.count(request["messages"], request.get("tools", [])),
                "synthetic_tokens_without_tools": profile.count(request["messages"], []),
                "num_ctx": request["options"]["num_ctx"],
                "num_predict": request["options"]["num_predict"],
            })
        data = {
            "arm": arm,
            "system_prompt_chars": len(chosen), "prefix_chars": len(prefixes[arm]),
            "prefix_utf8_bytes": len(prefixes[arm].encode()),
            "system_prompt_sha256": hashlib.sha256(chosen.encode()).hexdigest(),
            "requests": requests,
            "fixture_profile": profile.spec.model_dump(),
            "threshold": 10000,
            "observed_character_check": bool(requests) and requests[-1]["total_message_chars"] < 10000,
        }
        Path(os.environ["CAPRI_PROBE_OUTPUT"]).write_text(json.dumps(data, indent=2) + "\n")
