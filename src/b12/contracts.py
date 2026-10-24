"""Версійовані DTO. Actor створює лише довірений контрольний шлях."""

import math
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _identifier(value: str) -> str:
    if (
        not value.strip()
        or value != value.strip()
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ValueError("identifier must be nonblank without surrounding whitespace or controls")
    return value


Identifier = Annotated[str, Field(min_length=1, max_length=128)]


def _uuid(value: str) -> str:
    UUID(value)
    return value


def _json_value(value: Any) -> Any:
    """Відхилити не-JSON payload до передачі у transport або persistence."""
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, list):
        for child in value:
            _json_value(child)
        return value
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for child in value.values():
            _json_value(child)
        return value
    raise ValueError("payload must contain only finite JSON values and string object keys")


class _Contract(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", validate_default=True)

    schema_version: Literal[1] = 1

    @field_validator("schema_version", mode="before")
    @classmethod
    def _version_is_integer(cls, value: Any) -> int:
        if type(value) is not int:
            raise ValueError("schema version must be an integer")
        return value


class Actor(_Contract):
    model_config = ConfigDict(frozen=True)

    id: Identifier
    owner: bool = False
    consent: bool = False

    _validate_id = field_validator("id")(_identifier)


class MemoryRecord(_Contract):
    id: str
    owner_id: Identifier
    kind: Identifier
    text: Annotated[str, Field(min_length=1)]
    source: Annotated[str, Field(min_length=1)]
    created_at: str
    evidence_ids: tuple[str, ...] = ()

    _validate_id = field_validator("id")(_uuid)
    _validate_identifiers = field_validator("owner_id", "kind", "source")(_identifier)

    @field_validator("text")
    @classmethod
    def _text_has_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("memory text must be nonblank")
        return value

    @field_validator("created_at")
    @classmethod
    def _timestamp_is_utc(cls, value: str) -> str:
        timestamp = datetime.fromisoformat(value)
        if (
            "T" not in value
            or not value.endswith(("Z", "+00:00"))
            or timestamp.utcoffset() != timedelta(0)
        ):
            raise ValueError("created_at must be an ISO8601 UTC timestamp")
        return value

    @field_validator("evidence_ids")
    @classmethod
    def _evidence_is_uuid(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for evidence_id in value:
            _uuid(evidence_id)
        return value


class ToolCall(_Contract):
    id: Identifier
    name: Identifier
    arguments: dict[str, Any]
    turn_id: str | None = None
    task_id: str | None = None

    _validate_identifiers = field_validator("id", "name")(_identifier)
    _validate_arguments = field_validator("arguments")(_json_value)

    @field_validator("turn_id", "task_id")
    @classmethod
    def _origin_is_uuid(cls, value: str | None) -> str | None:
        return _uuid(value) if value is not None else None


class ToolResult(_Contract):
    call_id: Identifier
    name: Identifier
    status: Identifier
    content: dict[str, Any]
    duration_ms: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0
    error_code: Identifier | None = None
    truncated: bool = False
    side_effects: tuple[dict[str, Any], ...] = ()
    outcome_unknown: bool = False

    _validate_identifiers = field_validator("call_id", "name", "status")(_identifier)
    _validate_content = field_validator("content")(_json_value)

    @field_validator("error_code")
    @classmethod
    def _error_is_identifier(cls, value: str | None) -> str | None:
        return _identifier(value) if value is not None else None

    @field_validator("side_effects")
    @classmethod
    def _effects_are_json(cls, value: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
        for effect in value:
            _json_value(effect)
        return value


class ModelReply(_Contract):
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    metrics: dict[str, Any] = Field(default_factory=dict)
    finish_reason: Identifier = "stop"

    _validate_metrics = field_validator("metrics")(_json_value)
    _validate_finish = field_validator("finish_reason")(_identifier)
