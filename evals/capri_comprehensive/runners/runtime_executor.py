"""Run scenario turns through the real B-12 runtime instead of a raw model call.

`ScenarioRunner._call_ollama_bridge` sends the model a harness-written system prompt that
lists every scenario memory, whoever owns it. That measures the bare model, not Capri:
actor isolation, consent, the persona, recall and the tool registry are all bypassed (for
example, MEM-05 put the owner's secret into the guest's prompt).

`RuntimeTurnExecutor` gives each scenario a fresh state directory, creates its actors with
their owner/consent flags, writes its memories into the actor's own namespace at their
scenario dates, and answers each turn with `Agent.turn` under the grant the API would
issue (owner: `owner_capabilities`; guest: `GUEST_CAPABILITIES`). Nothing is approved on
the scenario's behalf: a destructive call stays `approval_pending`.

Host tools act on the real filesystem with the user's rights, so the suite that uses this
executor must run inside a filesystem sandbox (`runners/sandboxed_suite.sh`).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from evals.capri_comprehensive.runners.live_components import (
    LONG_MODEL,
    _bolt_settings,
    _model_settings,
    _warped_now,
)

TURN_TIMEOUT_S = 600.0


def model_templates(state_dir: Path) -> dict[str, Any]:
    """Settings per model alias, resolved now: the scenario sandbox later replaces HOME."""
    return {
        # Capri's own defaults for Bolt (Settings: 4096 context, 1024 output tokens).
        "pinned_primary": _bolt_settings(state_dir).model_copy(
            update={"num_ctx": 4096, "output_tokens": 1024}
        ),
        "any_swappable": _model_settings(state_dir),
    }


def settings_for(scenario, state_dir: Path, templates: dict[str, Any] | None = None):
    """Runtime settings for a scenario: pinned Bolt or the swappable gemma4:12b."""
    runtime = scenario.pre_conditions.runtime_settings
    templates = templates or model_templates(state_dir)
    alias = "any_swappable" if runtime.model == "any_swappable" else "pinned_primary"
    settings = templates[alias]
    update: dict[str, Any] = {
        "state_dir": Path(state_dir), "quiet_start": "00:00", "quiet_end": "00:00",
    }
    if runtime.num_ctx:
        # Never below the deployment's own context: the scenario sizes were written for a
        # bare model call, and B-12's system prompt with tool schemas needs more room.
        update["num_ctx"] = max(runtime.num_ctx, settings.num_ctx)
    if runtime.temperature is not None:
        update["temperature"] = runtime.temperature
    if getattr(runtime, "seed", None) is not None:
        update["seed"] = runtime.seed
    return settings.model_copy(update=update)


class RuntimeTurnExecutor:
    """Scenario-aware turn executor backed by `b12.runtime.open_runtime`."""

    def __init__(self, base_dir: Path, templates: dict[str, Any] | None = None):
        self.base_dir = Path(base_dir)
        self.templates = templates or model_templates(self.base_dir / "template")
        self.runtime = None
        self.actors: dict[str, Any] = {}
        self.sessions: dict[str, str] = {}
        self.workspace: Path | None = None
        self.model: str | None = None

    @contextlib.contextmanager
    def scenario(self, scenario, workspace: Path) -> Iterator[None]:
        import b12.memory as memory_module
        from b12.runtime import open_runtime

        state_dir = self.base_dir / scenario.id / "state"
        state_dir.parent.mkdir(parents=True, exist_ok=True)
        settings = settings_for(scenario, state_dir, self.templates)
        self.model = settings.model
        self.runtime = open_runtime(settings)
        self.workspace = Path(workspace)
        self.actors, self.sessions = {}, {}
        state = scenario.pre_conditions.initial_state
        try:
            specs = {a.id: a for a in state.actors}
            for actor_id in {"actor-owner-01", *specs, *(m.actor_id for m in state.memories)}:
                spec = specs.get(actor_id)
                owner = spec.owner if spec else actor_id == "actor-owner-01"
                consent = spec.consent if spec else True
                self.actors[actor_id] = self.runtime.control.create_actor(
                    owner=owner, consent=consent
                )
            real_now = memory_module._now
            try:
                for memory in state.memories:
                    actor = self.actors[memory.actor_id]
                    if not actor.consent:
                        continue  # no consent, no memory: the store would refuse it anyway
                    memory_module._now = _warped_now(memory.timestamp)
                    self.runtime.memory.remember(memory.text, actor)
            finally:
                memory_module._now = real_now
            for pref in state.preferences:
                self.runtime.goals.set_preference(
                    self.actors[pref.actor_id].id, pref.key, pref.value, "scenario initial state"
                )
            yield
        finally:
            self.runtime.close()
            self.runtime = None

    def _session(self, actor_id: str, new_session: bool) -> str:
        if new_session or actor_id not in self.sessions:
            self.sessions[actor_id] = self.runtime.control.create_session(
                self.actors[actor_id].id
            )
        return self.sessions[actor_id]

    def _grant(self, actor, session: str) -> tuple[str, str]:
        from b12.auth import GUEST_CAPABILITIES, owner_capabilities

        control, settings = self.runtime.control, self.runtime.settings
        task = control.create_task(session)
        if actor.owner:
            capabilities = owner_capabilities(settings)
            full = settings.host_access == "full"
        else:
            capabilities = tuple(sorted(GUEST_CAPABILITIES))
            full = False
        grant = control.issue_grant(
            actor.id, session, capabilities, task_id=task,
            ttl_s=TURN_TIMEOUT_S + 3600, full_execution=full,
        )
        return grant, task

    def run_turn(self, turn, turn_index: int, world_state: dict[str, Any]) -> dict[str, Any]:
        if turn.actor_id not in self.actors:
            self.actors[turn.actor_id] = self.runtime.control.create_actor(
                owner=False, consent=True
            )
        actor = self.actors[turn.actor_id]
        session = self._session(turn.actor_id, turn.new_session)
        grant, task = self._grant(actor, session)
        cwd = Path.cwd()
        os.chdir(self.workspace)  # relative paths in prompts name files of the scenario
        try:
            result = asyncio.run(self.runtime.agent.turn(
                session, grant, turn.input, task_id=task, timeout_s=TURN_TIMEOUT_S
            ))
        finally:
            os.chdir(cwd)
        metrics = list(result.model_metrics)
        ttft = next((m.get("ttft_s") for m in metrics if m.get("ttft_s")), None)
        content = result.content
        if result.state != "completed" and not content:
            content = f"[{result.state}: {result.error_code or 'no error code'}]"
        world_state.setdefault("runtime_turns", []).append({
            "turn": turn_index, "state": result.state, "error_code": result.error_code,
            "pending_operations": list(result.pending_operations),
            "evidence_ids": list(result.evidence_ids), "model": self.model,
        })
        return {
            "content": content,
            "tool_calls": [
                {"name": r.name, "status": r.status, "error_code": r.error_code}
                for r in result.tool_results
            ],
            "ttft_ms": round(ttft * 1000, 2) if ttft is not None else None,
            "tokens_prompt": sum(int(m.get("prompt_eval_count", 0) or 0) for m in metrics),
            "tokens_completion": sum(int(m.get("eval_count", 0) or 0) for m in metrics),
            "runtime_state": result.state,
        }


__all__ = ["LONG_MODEL", "RuntimeTurnExecutor", "settings_for"]
