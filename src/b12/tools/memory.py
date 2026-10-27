"""Memory/knowledge tools; global purge and turn revisions are trusted ports.

Ports are application-owned objects/callables, never model arguments. No local
MemoryStore.forget bool is presented as globally completed erasure.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pydantic import Field, field_validator

from b12.contracts import PurgeReceipt
from b12.control import ExecutionContext
from b12.tools._common import Args, EmptyArgs, clip, failure
from b12.tools.outcomes import HandlerOutcome, SideEffect
from b12.tools.policy import EffectGuard, Risk


class GlobalPurge(Protocol):
    async def purge(
        self, memory_id: str, context: ExecutionContext, guard: EffectGuard
    ) -> PurgeReceipt: ...


MemoryRevision = Callable[[ExecutionContext], int]


class SearchArgs(Args):
    query: str = Field(min_length=1, max_length=256)
    limit: int = Field(default=5, ge=1, le=10)


class StoreArgs(Args):
    text: str = Field(min_length=1, max_length=8192)
    kind: str = Field(default="fact", min_length=1, max_length=64)
    evidence_ids: list[str] = Field(
        default_factory=list,
        max_length=32,
        description="Optional UUIDs of existing evidence only; leave empty, never invent ids",
    )

    @field_validator("text")
    @classmethod
    def _bytes(cls, value):
        if len(value.encode()) > 8192 or not value.strip():
            raise ValueError("memory size/content limit")
        return value

    @field_validator("evidence_ids")
    @classmethod
    def _ids(cls, values):
        for value in values:
            UUID(value)
        return values


class ForgetArgs(Args):
    memory_id: str

    @field_validator("memory_id")
    @classmethod
    def _id(cls, value):
        UUID(value)
        return value


async def current_time(args, guard):
    guard.check()
    return HandlerOutcome(content={"utc": datetime.now(UTC).isoformat()})


def register(registry, *, memory=None, knowledge=None, purge=None, memory_revision=None):
    async def memory_search(args, guard):
        if memory is None:
            return failure("coordinator_unavailable")
        guard.check()
        actor = guard.store.resolve_actor(guard.context.actor_id)
        records = memory.search(args.query, actor, limit=args.limit)
        rows, truncated = [], False
        for record in records:
            text, cut = clip(record.text, 512)
            source, source_cut = clip(record.source, 128)
            truncated |= cut or source_cut
            rows.append(
                {
                    "id": record.id,
                    "text": text,
                    "source": source,
                    "kind": record.kind,
                    "created_at": record.created_at,
                    "evidence_ids": list(record.evidence_ids[:32]),
                }
            )
            truncated |= len(record.evidence_ids) > 32
        return HandlerOutcome(content={"records": rows}, truncated=truncated)

    async def memory_store(args, guard):
        if memory is None or memory_revision is None:
            return failure("coordinator_unavailable")
        guard.check()
        actor = guard.store.resolve_actor(guard.context.actor_id)
        try:
            expected_revision = memory_revision(guard.context)
        except Exception:
            return failure("coordinator_unavailable")
        if type(expected_revision) is not int or expected_revision < 0:
            return failure("coordinator_unavailable")
        guard.check()
        try:
            record = memory.remember(
                args.text,
                actor,
                kind=args.kind,
                source="tool:" + guard.operation_id,
                evidence_ids=tuple(args.evidence_ids),
                expected_deletion_revision=expected_revision,
            )
        except PermissionError:
            return failure("permission_denied")
        except ValueError:
            return failure("unsupported")
        except Exception:
            return HandlerOutcome(
                status="unknown",
                error_code="handler_failed",
                side_effects=(SideEffect(kind="memory_write", state="possible"),),
            )
        return HandlerOutcome(
            content={"id": record.id, "source": record.source},
            side_effects=(
                SideEffect(kind="memory_write", state="completed", evidence_ids=(record.id,)),
            ),
        )

    async def memory_forget(args, guard):
        if purge is None:
            return failure("coordinator_unavailable")
        guard.check()
        # Coordinator owns transitive stores, revision invalidation and final acknowledgement.
        try:
            receipt = await purge.purge(args.memory_id, guard.context, guard)
            receipt = PurgeReceipt.model_validate(receipt.model_dump(mode="python"), strict=True)
        except KeyError:
            # Coordinator rejected an unknown/foreign ID before any tombstone or hook.
            return failure("not_found")
        except (Exception, asyncio.CancelledError) as exc:
            return HandlerOutcome(
                status="unknown",
                error_code="cancelled"
                if isinstance(exc, asyncio.CancelledError)
                else "cleanup_failed",
                side_effects=(
                    SideEffect(
                        kind="memory_forget", state="possible", evidence_ids=(args.memory_id,)
                    ),
                ),
            )
        complete = receipt.state == "complete"
        data = receipt.model_dump(mode="json")
        data["target_ids"] = data["target_ids"][:64]
        data["pending_stores"] = data["pending_stores"][:64]
        return HandlerOutcome(
            status="completed" if complete else "unknown",
            error_code=None if complete else "cleanup_failed",
            content={"receipt": data},
            truncated=len(receipt.target_ids) > 64 or len(receipt.pending_stores) > 64,
            side_effects=(
                SideEffect(
                    kind="memory_forget",
                    state=("completed" if complete else "possible"),
                    evidence_ids=receipt.target_ids[:64],
                ),
            ),
        )

    async def knowledge_search(args, guard):
        if knowledge is None:
            return failure("coordinator_unavailable")
        guard.check()
        actor = guard.store.resolve_actor(guard.context.actor_id)
        hits, truncated = [], False
        for item in knowledge.search(args.query, actor, limit=args.limit):
            hit = {key: item[key] for key in ("evidence_id", "source_id", "revision", "score")}
            for key, bound in (("text", 256), ("source", 256), ("locator", 128)):
                hit[key], cut = clip(item[key], bound)
                truncated |= cut
            hits.append(hit)
        # The durable KnowledgeIndex ledger remains the delivery source for Task7;
        # this bounded preview never acknowledges or drops work from that ledger.
        receipts = knowledge.operation_receipts(actor)
        preview = []
        for item in receipts[-4:]:
            data = {key: item[key] for key in ("operation_id", "state", "error_code")}
            ids = item["invalidated_evidence_ids"]
            data["invalidated_evidence_ids"] = ids[:64]
            truncated |= len(ids) > 64
            preview.append(data)
        return HandlerOutcome(
            content={"hits": hits, "invalidation_receipts": preview},
            truncated=truncated or len(receipts) > 4,
        )

    registry.register(
        "memory_search",
        "Search exact-actor canonical memory with bounded evidence",
        SearchArgs,
        memory_search,
        "memory.read",
    )
    registry.register(
        "memory_store",
        "Store memory using trusted turn deletion revision and provenance",
        StoreArgs,
        memory_store,
        "memory.write",
    )
    registry.register(
        "memory_forget",
        "Request global purge through registered coordinator",
        ForgetArgs,
        memory_forget,
        "memory.forget",
        risk=Risk.DESTRUCTIVE,
    )
    registry.register(
        "knowledge_search",
        "Search actor-scoped derived knowledge and preview invalidations",
        SearchArgs,
        knowledge_search,
        "knowledge.read",
    )
    registry.register("current_time", "Read current UTC time", EmptyArgs, current_time, "time.read")
