"""Trusted handler return contract. Registry alone owns result/control identity.

failed is a handler certification that NO effect occurred. Partial/possible effects
must use unknown. This is a trusted-code assertion, not detection of OS effects.
Content/effect metadata are actor-authorized transient results, never audit payload.
Handlers must bound output while collecting it; this final 64KiB check cannot bound
memory they already allocated. IDs in evidence/artifact references are generated UUIDs.
"""

import copy
import json
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from b12.contracts import _json_value

MAX_OUTCOME_BYTES = 64 * 1024
HandlerErrorCode = Literal[
    "handler_failed",
    "permission_denied",
    "not_found",
    "unsupported",
    "process_failed",
    "network_failed",
    "network_denied",
    "cleanup_failed",
    "deadline_exceeded",
    "cancelled",
    "coordinator_unavailable",
]


class SideEffect(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, validate_default=True)

    kind: Literal[
        "file_write",
        "process_execution",
        "http_request",
        "memory_write",
        "memory_forget",
        "knowledge_write",
        "mcp_call",
    ]
    state: Literal["completed", "possible"]
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=64)
    artifact_ids: tuple[str, ...] = Field(default=(), max_length=64)

    @field_validator("evidence_ids", "artifact_ids")
    @classmethod
    def _references_are_uuid(cls, values):
        for value in values:
            UUID(value)
        return values


class HandlerOutcome(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True, validate_default=True)

    status: Literal["completed", "failed", "unknown"] = "completed"
    content: dict[str, Any] = Field(default_factory=dict)
    side_effects: tuple[SideEffect, ...] = Field(default=(), max_length=64)
    truncated: bool = False
    error_code: HandlerErrorCode | None = None

    _finite_content = field_validator("content")(_json_value)

    @model_validator(mode="after")
    def _coherent_and_bounded(self):
        if self.status == "completed":
            if self.error_code is not None or any(
                e.state != "completed" for e in self.side_effects
            ):
                raise ValueError("completed requires confirmed effects and no error")
        elif self.error_code is None:
            raise ValueError("failure or uncertainty requires a fixed error code")
        if self.status == "failed" and self.side_effects:
            raise ValueError("failed certifies no effects; partial effects require unknown")
        if (
            len(
                json.dumps(
                    self.model_dump(mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
            )
            > MAX_OUTCOME_BYTES
        ):
            raise ValueError("handler outcome exceeds 64KiB")
        return self


def validated_outcome(value: Any) -> HandlerOutcome:
    """Fresh strict snapshot AFTER await, including constructed/mutated nested DTOs."""
    if (
        type(value) is not HandlerOutcome
        or set(value.__dict__) != set(HandlerOutcome.model_fields)
        or value.__pydantic_extra__
    ):
        raise ValueError("typed handler outcome required")
    for effect in value.side_effects:
        if (
            type(effect) is not SideEffect
            or set(effect.__dict__) != set(SideEffect.model_fields)
            or effect.__pydantic_extra__
        ):
            raise ValueError("typed effect metadata required")
    snapshot = copy.deepcopy(value.model_dump(mode="python", warnings=False))
    return HandlerOutcome.model_validate(snapshot, strict=True)
