"""settings.memory_grounding: grounding rules reach the memory_store schema and reflection."""

from b12.runtime import open_runtime
from b12.tools.memory import GROUNDING_RULE


def _store_description(runtime) -> str:
    for tool in runtime.registry._tools.values():
        if tool.schema["function"]["name"] == "memory_store":
            return tool.schema["function"]["description"]
    raise AssertionError("memory_store is not registered")


def test_grounding_rule_is_in_the_store_schema_only_with_the_flag(scripted_ollama, tmp_path):
    _, base = scripted_ollama
    for flag in (False, True):
        runtime = open_runtime(
            base.model_copy(update={"state_dir": tmp_path / str(flag), "memory_grounding": flag})
        )
        try:
            assert (GROUNDING_RULE in _store_description(runtime)) is flag
        finally:
            runtime.close()


async def test_reflection_prompt_carries_grounding_and_accepts_no_hypothesis(
    scripted_ollama, tmp_path
):
    from b12.reflection import Reflector

    state, base = scripted_ollama
    runtime = open_runtime(
        base.model_copy(update={"state_dir": tmp_path / "r", "memory_grounding": True})
    )
    try:
        actor = runtime.control.create_actor(owner=True, consent=True)
        runtime.memory.remember("Власник попросив сьогодні коротку відповідь.", actor)
        runtime.memory.remember("Власник працює над B-12.", actor)
        state["script"] = [{"content": '{"hypothesis": "", "evidence_ids": []}'}]
        outcome = await Reflector(runtime).reflect(actor)
        system = state["requests"][-1]["messages"][0]["content"]
        assert "разове прохання не є постійним вподобанням" in system
        assert outcome == {"state": "skipped", "reason": "no_hypothesis"}
    finally:
        runtime.close()
