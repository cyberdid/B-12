"""Global purge over the canonical durable outbox (MemoryStore purge tables).

Registered managed stores: canonical (payload, FTS, WAL checkpoint), sessions
(every evidence-tagged turn, checkpoint and volatile copy), active_turns (cancel and
invalidate in-flight turns of the actor), backups (managed copies created in affected
turns) and provider_cache (model-level unload of the dedicated alias; not per-actor
erasure). Complete only after every hook acknowledged. Failures stay pending/failed
and are retried by resume() at startup. Unmanaged originals/snapshots are untouched.
"""

import logging

from b12.contracts import Actor, PurgeReceipt

log = logging.getLogger(__name__)

STORES = ("sessions", "goals", "active_turns", "backups", "provider_cache")


class PurgeCoordinator:
    def __init__(
        self, *, control, memory, sessions, backups=None, knowledge=None, agent=None, goals=None
    ):
        self.control, self.memory, self.sessions, self.goals = control, memory, sessions, goals
        self.backups, self.knowledge, self.agent = backups, knowledge, agent

    async def purge(self, memory_id: str, context, guard) -> PurgeReceipt:
        """GlobalPurge port for the memory_forget tool (approval enforced by registry)."""
        actor = self.control.resolve_actor(context.actor_id)
        guard.check()
        receipt = self.memory.begin_purge(memory_id, actor, stores=STORES)
        return await self._run(receipt, actor, origin_turn=context.turn_id)

    async def forget(self, memory_id: str, actor_id: str) -> PurgeReceipt:
        """Trusted owner-control path (CLI/API), outside any model turn."""
        actor = self.control.resolve_actor(actor_id)
        receipt = self.memory.begin_purge(memory_id, actor, stores=STORES)
        return await self._run(receipt, actor, origin_turn=None)

    async def resume(self) -> list[PurgeReceipt]:
        """Startup recovery before serving data: retry pending hooks and invalidations."""
        receipts = []
        for actor_id in self.control.actor_ids():
            actor = self.control.resolve_actor(actor_id)
            for receipt in self.memory.pending_purges(actor):
                receipts.append(await self._run(receipt, actor, origin_turn=None))
            await self.sync_knowledge(actor)
        return receipts

    async def _hook(self, store: str, receipt: PurgeReceipt, actor: Actor, origin_turn) -> bool:
        targets = receipt.target_ids
        if store == "sessions":
            self.sessions.purge_evidence(receipt.operation_id, actor.id, targets)
            if self.agent is not None:
                self.agent.purge_volatile(actor.id, targets)
            return True
        if store == "goals":
            if self.goals is not None:
                self.goals.purge_evidence(actor.id, targets)
            return True
        if store == "active_turns":
            if self.agent is None:
                return True
            return await self.agent.invalidate_active(actor.id, exclude=origin_turn)
        if store == "backups":
            if self.backups is None:
                return True
            turns = self.sessions.purge_evidence(receipt.operation_id, actor.id, ())
            result = self.backups.purge(actor.id, turn_ids=tuple(turns))
            return result["state"] == "complete"
        if store == "provider_cache":
            if self.agent is None:
                return True
            return await self.agent.reset_provider()
        raise ValueError("unregistered purge store")

    async def _run(self, receipt: PurgeReceipt, actor: Actor, *, origin_turn) -> PurgeReceipt:
        operation = receipt.operation_id
        for store in receipt.pending_stores:
            if store == "canonical":
                receipt = self.memory.acknowledge_purge(operation, "canonical", actor)
                continue
            # Backups derive affected turns from the sessions ledger; wait for it.
            if store == "backups" and "sessions" in receipt.pending_stores:
                continue
            try:
                done = await self._hook(store, receipt, actor, origin_turn)
            except Exception:
                log.exception("purge hook failed")
                receipt = self.memory.acknowledge_purge(
                    operation, store, actor, error_code=f"{store}_failed"
                )
                continue
            if done:
                receipt = self.memory.acknowledge_purge(operation, store, actor)
        return self.memory.purge_receipt(operation, actor)

    async def sync_knowledge(self, actor: Actor) -> list[str]:
        """Deliver document invalidations to dependent copies; idempotent per operation."""
        if self.knowledge is None:
            return []
        applied = []
        for receipt in self.knowledge.operation_receipts(actor):
            operation = receipt["operation_id"]
            ids = tuple(receipt["invalidated_evidence_ids"])
            if not ids or self.sessions.invalidation_applied(operation):
                continue
            self.sessions.purge_evidence(operation, actor.id, ids)
            if self.goals is not None:
                self.goals.purge_evidence(actor.id, ids)
            if self.agent is not None:
                self.agent.purge_volatile(actor.id, ids)
                if not await self.agent.reset_provider():
                    continue  # retried on the next sync; old text may remain in provider KV
            self.sessions.mark_invalidation_applied(operation)
            applied.append(operation)
        return applied
