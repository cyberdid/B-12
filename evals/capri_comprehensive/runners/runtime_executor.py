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
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from evals.capri_comprehensive.runners.live_components import (
    LONG_MODEL,
    _bolt_settings,
    _model_settings,
    _warped_now,
)

TURN_TIMEOUT_S = 600.0


def model_templates(state_dir: Path, variant: str = "") -> dict[str, Any]:
    """Settings per model alias, resolved now: the scenario sandbox later replaces HOME.

    variant "deployed" is the owner's running configuration: gemma4:12b for every
    scenario, with semantic recall through the EmbeddingGemma 2 bridge. "deployed-<name>"
    is the same configuration with the model named by B12_EVAL_MODEL.
    """
    if variant.startswith("deployed"):
        from evals.capri_comprehensive.runners.live_components import SEMANTIC_PYTHON

        gemma = _model_settings(state_dir).model_copy(update={"embedding_python": SEMANTIC_PYTHON})
        return {"pinned_primary": gemma, "any_swappable": gemma}
    return {
        # Capri's own defaults for Bolt (Settings: 8192 context, 1024 output tokens).
        "pinned_primary": _bolt_settings(state_dir).model_copy(
            update={"num_ctx": 8192, "output_tokens": 1024}
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
        "state_dir": Path(state_dir),
        "quiet_start": "00:00",
        "quiet_end": "00:00",
        "sudo_access": runtime.sudo_access,
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

    def __init__(
        self,
        base_dir: Path,
        templates: dict[str, Any] | None = None,
        variant: str = "",
        trace_observer: Callable | None = None,
    ):
        self.base_dir = Path(base_dir)
        self.trace_observer = trace_observer
        self.templates = templates or model_templates(self.base_dir / "template", variant)
        if variant.startswith("deployed"):
            # The scenario sandbox replaces HOME; the embedding bridge must still find the
            # cached weights under the real one.
            os.environ.setdefault("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
        self.runtime = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.actors: dict[str, Any] = {}
        self.sessions: dict[str, str] = {}
        self.seeded_memory_ids: set[str] = set()
        self.workspace: Path | None = None
        self.model: str | None = None
        self._trace_collectors = {}

    @contextlib.contextmanager
    def scenario(self, scenario, workspace: Path) -> Iterator[None]:
        import b12.memory as memory_module
        from b12.runtime import open_runtime

        state_dir = self.base_dir / scenario.id / "state"
        state_dir.parent.mkdir(parents=True, exist_ok=True)
        settings = settings_for(scenario, state_dir, self.templates)
        self.model = settings.model
        self.workspace = Path(workspace)
        # The scenario's files are the owner's files: the agent tells the model its home
        # directory (Path.home()), so home is the workspace that holds them. Set HOME and
        # XDG_CONFIG_HOME before open_runtime: its protected-path policy is resolved during
        # construction and must cover this scenario's config root, not the host's.
        previous_home = os.environ.get("HOME")
        previous_xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
        os.environ["HOME"] = str(self.workspace)
        os.environ["XDG_CONFIG_HOME"] = str(self.workspace / ".config")
        self.actors, self.sessions = {}, {}
        self.seeded_memory_ids = set()
        self._trace_collectors = {}
        state = scenario.pre_conditions.initial_state
        try:
            # One event loop for all turns of the scenario: the embedding bridge process
            # and its lock belong to the loop that started them.
            self.loop = asyncio.new_event_loop()
            self.runtime = open_runtime(settings)
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
                    record = self.runtime.memory.remember(memory.text, actor)
                    self.seeded_memory_ids.add(record.id)
            finally:
                memory_module._now = real_now
            for pref in state.preferences:
                self.runtime.goals.set_preference(
                    self.actors[pref.actor_id].id, pref.key, pref.value, "scenario initial state"
                )
            yield
        finally:
            for key, previous in (
                ("HOME", previous_home),
                ("XDG_CONFIG_HOME", previous_xdg_config_home),
            ):
                if previous is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = previous
            if self.runtime is not None:
                self.runtime.close()
                self.runtime = None
            if self.loop is not None:
                self.loop.close()
                self.loop = None

    def _session(self, actor_id: str, new_session: bool) -> str:
        if new_session or actor_id not in self.sessions:
            self.sessions[actor_id] = self.runtime.control.create_session(self.actors[actor_id].id)
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
            actor.id,
            session,
            capabilities,
            task_id=task,
            ttl_s=TURN_TIMEOUT_S + 3600,
            full_execution=full,
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
            result = self.loop.run_until_complete(
                self.runtime.agent.turn(
                    session, grant, turn.input, task_id=task, timeout_s=TURN_TIMEOUT_S
                )
            )
        finally:
            os.chdir(cwd)
        if self.trace_observer is not None:
            from evals.unified.trace import TraceCollector

            collector = TraceCollector()
            for event in result.events:
                collector.record(event)
            collector.record_turn_result(result)
            self._trace_collectors[turn_index] = collector
        metrics = list(result.model_metrics)
        ttft = next((m.get("ttft_s") for m in metrics if m.get("ttft_s")), None)
        content = result.content
        seeded_memory_evidence_count = len(self.seeded_memory_ids.intersection(result.evidence_ids))
        reported_tool_calls = [
            {"name": r.name, "status": r.status, "error_code": r.error_code}
            for r in result.tool_results
        ]
        reported_tool_calls.extend(
            {
                "name": event.data.get("name"),
                "status": "approval_pending",
                "error_code": None,
            }
            for event in result.events
            if event.type == "approval_pending" and event.data.get("name")
        )
        if result.state != "completed" and not content:
            content = f"[{result.state}: {result.error_code or 'no error code'}]"
        world_state.setdefault("runtime_turns", []).append(
            {
                "turn": turn_index,
                "state": result.state,
                "error_code": result.error_code,
                "pending_operations": list(result.pending_operations),
                "evidence_ids": list(result.evidence_ids),
                "seeded_memory_evidence_count": seeded_memory_evidence_count,
                "model": self.model,
            }
        )
        return {
            "content": content,
            "tool_calls": reported_tool_calls,
            "ttft_ms": round(ttft * 1000, 2) if ttft is not None else None,
            "tokens_prompt": sum(int(m.get("prompt_eval_count", 0) or 0) for m in metrics),
            "tokens_completion": sum(int(m.get("eval_count", 0) or 0) for m in metrics),
            "runtime_state": result.state,
            "seeded_memory_evidence_count": seeded_memory_evidence_count,
        }

    def record_verification(self, turn_index, passed, method, criteria, *, inconclusive=False):
        """Finalize the captured trace with the evaluator verdict, without storing its text."""
        collector = self._trace_collectors.pop(turn_index, None)
        if collector is None:
            return
        status = "inconclusive" if inconclusive else "pass" if passed else "fail"
        collector.record_verification(status, method, criteria)
        self.trace_observer(turn_index, collector)


__all__ = ["LONG_MODEL", "RuntimeTurnExecutor", "settings_for"]
