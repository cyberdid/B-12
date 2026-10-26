"""Application factory: one owned set of stores, tools, agent and purge coordinator.

Layout under Settings.state_dir (private): control/, memory/, knowledge/, backups/,
sessions/. CLI/API/scheduler/audio share this object instead of building their own.
"""

from dataclasses import dataclass, field

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
from b12.service import Operations
from b12.sessions import SessionStore
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
    mcp_servers: list = field(default_factory=list)

    def close(self):
        for server in self.mcp_servers:
            server.close()
        if self.agent.semantic is not None:
            self.agent.semantic.close()
        for store in (
            self.attention,
            self.goals,
            self.backups,
            self.knowledge,
            self.sessions,
            self.memory,
            self.control,
        ):
            try:
                store.close()
            except Exception:  # noqa: BLE001 - closing must continue for every store
                pass


def open_runtime(settings: Settings, *, model=None) -> Runtime:
    root = settings.state_dir
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    control = ControlStore(root / "control")
    memory = MemoryStore(root / "memory" / "memory.sqlite3")
    knowledge = KnowledgeIndex(root / "knowledge")
    backups = BackupStore(root / "backups")
    sessions = SessionStore(root / "sessions")
    goals = GoalStore(root / "goals")
    attention = AttentionPolicy(root / "attention", settings)
    operations = Operations(root)
    registry = ToolRegistry(control, timeout_s=settings.tool_timeout_s)
    model = model or OllamaModel(settings)
    agent = Agent(
        settings,
        control=control,
        registry=registry,
        model=model,
        sessions=sessions,
        memory=memory,
        resolver=EvidenceResolver(memory, knowledge),
    )
    purge = PurgeCoordinator(
        control=control,
        memory=memory,
        sessions=sessions,
        backups=backups,
        knowledge=knowledge,
        agent=agent,
        goals=goals,
        operations=operations,
    )
    agent.purge = purge
    if settings.embedding_python:
        from b12.semantic import BridgeEmbedder, SemanticIndex

        agent.semantic = SemanticIndex(
            root / "semantic",
            BridgeEmbedder(settings.embedding_python, backend=settings.embedding_backend),
            memory,
        )
    register_host_tools(
        registry,
        backups=backups,
        memory=memory,
        knowledge=knowledge,
        purge=purge,
        memory_revision=agent.memory_revision,
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
    )
