"""Application factory: one owned set of stores, tools, agent and purge coordinator.

Layout under Settings.state_dir (private): control/, memory/, knowledge/, backups/,
sessions/. CLI/API/scheduler/audio share this object instead of building their own.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from b12.agent import Agent
from b12.attention import AttentionPolicy
from b12.config import Settings
from b12.control import ControlStore
from b12.evidence import EvidenceResolver
from b12.goals import GoalStore
from b12.memory import MemoryStore
from b12.model import OllamaModel
from b12.purge import PurgeCoordinator
from b12.retrieval import KnowledgeIndex
from b12.schedules import ScheduleStore
from b12.service import Operations
from b12.sessions import SessionStore
from b12.skills import SkillStore
from b12.tools import register_host_tools
from b12.tools.filesystem import BackupStore
from b12.tools.registry import ToolRegistry


@dataclass
class Runtime:
    settings: Settings
    control: ControlStore
    memory: MemoryStore
    knowledge: KnowledgeIndex
    backups: BackupStore
    sessions: SessionStore
    registry: ToolRegistry
    model: OllamaModel
    agent: Agent
    purge: PurgeCoordinator
    goals: GoalStore
    attention: AttentionPolicy
    operations: Operations
    schedules: ScheduleStore | None = None
    skills: SkillStore | None = None
    mcp_servers: list = field(default_factory=list)
    speakers: object = None

    def close(self):
        for server in self.mcp_servers:
            server.close()
        if self.agent.semantic is not None:
            self.agent.semantic.close()
        if self.speakers is not None:
            self.speakers.close()
        for store in (
            self.attention,
            self.schedules,
            self.goals,
            self.backups,
            self.knowledge,
            self.sessions,
            self.memory,
            self.control,
        ):
            if store is None:
                continue
            try:
                store.close()
            except Exception:  # noqa: BLE001 - closing must continue for every store
                pass


def embedder_env(settings: Settings) -> dict[str, str]:
    """Environment for the embedding bridge process (CPU unless told otherwise)."""
    return {"CUDA_VISIBLE_DEVICES": ""} if settings.embedding_device == "cpu" else {}


def open_runtime(settings: Settings, *, model=None) -> Runtime:
    root = settings.state_dir
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    control = ControlStore(root / "control")
    memory = MemoryStore(root / "memory" / "memory.sqlite3")
    memory.min_free_bytes = settings.min_free_mb * 2**20
    knowledge = KnowledgeIndex(root / "knowledge")
    memory.document_resolver = knowledge.resolve_evidence  # citations are checked at write time
    backups = BackupStore(root / "backups")
    sessions = SessionStore(root / "sessions")

    goals = GoalStore(root / "goals")
    schedules = ScheduleStore(root / "goals")
    skills_store = SkillStore(root / "skills")

    def _report_forgotten_skills(actor_id: str, forgotten: list[str]) -> None:
        for name in forgotten:
            goals.add_proposal(
                actor_id,
                f"skill:{name}",
                f"Навичка «{name}» втратила вихідну сесію і позначена source_forgotten "
                "(файл збережено для перевірки власником).",
                delivered=False,
                reason="source_forgotten",
                attention_id=None,
                tags={},
                decision="inbox",
            )

    def _on_clear_turns(actor_id: str, turn_ids: list[str]) -> None:
        actor = control.resolve_actor(actor_id)
        for turn_id in turn_ids:
            memory.forget_by_locator(actor, f"turn:{turn_id}", source="post_turn_review")
        _report_forgotten_skills(
            actor_id, skills_store.mark_source_forgotten(turn_ids=turn_ids, actor_id=actor_id)
        )

    def _on_clear_session(actor_id: str, session_id: str) -> None:
        _report_forgotten_skills(
            actor_id,
            skills_store.mark_source_forgotten(session_ids=[session_id], actor_id=actor_id),
        )

    sessions.on_clear_turns = _on_clear_turns
    sessions.on_clear_session = _on_clear_session
    attention = AttentionPolicy(root / "attention", settings)
    operations = Operations(root)
    registry = ToolRegistry(control, timeout_s=settings.tool_timeout_s)
    model = model or OllamaModel(settings)
    resolver = EvidenceResolver(memory, knowledge)
    agent = Agent(
        settings,
        control=control,
        registry=registry,
        model=model,
        sessions=sessions,
        memory=memory,
        resolver=resolver,
        tool_result_bytes=settings.tool_result_bytes,
    )
    from b12.audio.speaker import SpeakerStore

    speakers = SpeakerStore(settings.state_dir / "voice" / "speakers.sqlite3")
    purge = PurgeCoordinator(
        control=control,
        memory=memory,
        sessions=sessions,
        backups=backups,
        knowledge=knowledge,
        agent=agent,
        goals=goals,
        operations=operations,
        speakers=speakers,
    )
    agent.purge = purge
    agent.goals = goals  # current preferences of the speaker are shown to the model
    agent.schedules = schedules
    agent.skills = skills_store
    if settings.embedding_python:
        from b12.semantic import BridgeEmbedder, SemanticIndex

        agent.semantic = SemanticIndex(
            root / "semantic",
            BridgeEmbedder(
                settings.embedding_python,
                backend=settings.embedding_backend,
                env=embedder_env(settings),
            ),
            memory,
        )
    register_host_tools(
        registry,
        backups=backups,
        memory=memory,
        knowledge=knowledge,
        purge=purge,
        memory_revision=agent.memory_revision,
        sudo=settings.host_access == "full" and settings.sudo_access == "approval",
        memory_temporal=settings.memory_temporal,
        memory_as_of=settings.memory_as_of,
        memory_scoped=settings.memory_scoped,
        memory_ranking=settings.memory_ranking,
        verify_writes=settings.verify_writes,
        memory_grounding=settings.memory_grounding,
        memory_taint=settings.memory_taint,
        turn_tainted=agent.turn_tainted,
        sessions=sessions,
        resolver=resolver,
        session_search=settings.session_search,
        clarify_tool=settings.clarify_tool,
        skill_store=skills_store,
        skills=settings.skills,
    )
    if not settings.forget_requires_approval:
        registry.approval_exempt.add("memory_forget")
    registry.network_allow = settings.network_allow
    registry.ledger = settings.task_ledger
    registry.goal_contract = settings.goal_contract
    registry.goals = goals
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    registry.protected_paths = tuple(
        os.path.realpath(path) for path in (settings.state_dir, config_home / "b12")
    )
    return Runtime(
        settings,
        control,
        memory,
        knowledge,
        backups,
        sessions,
        registry,
        model,
        agent,
        purge,
        goals,
        attention,
        operations,
        schedules=schedules,
        skills=skills_store,
        speakers=speakers,
    )
