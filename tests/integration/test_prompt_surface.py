"""The prompt surface: the exact system prompt and tool schemas a stock owner turn sends.

A one-line change elsewhere (a flag default, a tool description, persona text) can rewrite what
the model sees without the diff showing it. The rendered surface is committed and compared;
a change is reviewed as a change of the fixture. Idea from Hermes Agent's prompt-surface CI.

Regenerate after an intended change:
    B12_UPDATE_PROMPT_SURFACE=1 .venv/bin/python -m pytest tests/integration/test_prompt_surface.py
"""

import json
import os
import pwd
from datetime import UTC, datetime
from pathlib import Path

import pytest

from b12.auth import owner_capabilities
from b12.runtime import open_runtime

PINNED = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "prompt_surface"


async def _render(base, state_dir: Path, state) -> dict:
    runtime = open_runtime(base.model_copy(update={"state_dir": state_dir}))
    try:
        runtime.agent.clock = lambda: PINNED
        actor = runtime.control.create_actor(owner=True, consent=True)
        session = runtime.control.create_session(actor.id)
        task = runtime.control.create_task(session)
        grant = runtime.control.issue_grant(
            actor.id, session, owner_capabilities(runtime.settings), task_id=task, ttl_s=600
        )
        state["script"] = [{"content": "Привіт."}]
        await runtime.agent.turn(session, grant, "Привіт!", task_id=task, timeout_s=60)
    finally:
        runtime.close()
    request = state["requests"][-1]
    text = json.dumps(
        {
            "system": request["messages"][0]["content"],
            "tools": sorted(request.get("tools") or [], key=lambda t: t["function"]["name"]),
        },
        ensure_ascii=False,
        indent=1,
        sort_keys=True,
    )
    text = text.replace(str(state_dir), "<STATE_DIR>")
    for home in {str(Path.home()), pwd.getpwuid(os.getuid()).pw_dir}:  # HOME and the passwd entry
        text = text.replace(home, "<HOME>")
    return json.loads(text)


@pytest.mark.parametrize("name", ["owner_default"])
async def test_prompt_surface_matches_the_committed_snapshot(scripted_ollama, tmp_path, name):
    state, base = scripted_ollama
    surface = await _render(base, tmp_path / "state", state)
    fixture = FIXTURES / f"{name}.json"
    rendered = json.dumps(surface, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if os.environ.get("B12_UPDATE_PROMPT_SURFACE") == "1":
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_text(rendered, encoding="utf-8")
    assert fixture.exists(), "no snapshot yet: run with B12_UPDATE_PROMPT_SURFACE=1"
    assert rendered == fixture.read_text(encoding="utf-8"), (
        "the prompt surface changed; review the diff and regenerate the snapshot"
    )
