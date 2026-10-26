"""Strict typed dispatch with current server control and durable no-replay state.

schemas(ctx) returns fresh JSON copies for ContextBuilder BEFORE admission.
execute(call, ctx) replaces the old Actor/grant dict sketch: DTOs are not proof.
Handlers are trusted async (args, EffectGuard) -> HandlerOutcome, cooperative,
nonblocking, and must recheck guard before each additional effect/persistence.
There is no late model request mutation, sync thread offload or auto-resume here.
"""

import asyncio
import copy
import inspect
import math
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from b12.contracts import ToolCall, ToolResult
from b12.control import ControlError, ControlStore, ExecutionContext, arguments_digest
from b12.tools.outcomes import HandlerOutcome, validated_outcome
from b12.tools.policy import EffectGuard, Risk

Handler = Callable[[BaseModel, EffectGuard], Awaitable[HandlerOutcome]]
_UNCALIBRATED_SCHEMA = frozenset({"anyOf", "oneOf", "allOf", "$ref", "$defs", "not"})


@dataclass(frozen=True)
class _Tool:
    name: str
    description: str
    model: type[BaseModel]
    handler: Handler
    capability: str
    risk: Risk
    schema: dict


class ToolRegistry:
    def __init__(self, control: ControlStore, *, timeout_s: float = 30):
        if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("positive finite timeout required")
        self.control, self.timeout_s = control, timeout_s
        self._tools: dict[str, _Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        argument_model: type[BaseModel],
        handler: Handler,
        capability: str,
        *,
        risk: Risk | str = Risk.TYPED,
    ):
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]{0,127}", name):
            raise ValueError("invalid trusted tool name")
        if name in self._tools:
            raise ValueError("duplicate tool")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("description required")
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]{0,127}", capability):
            raise ValueError("invalid capability")
        if (
            not isinstance(argument_model, type)
            or not issubclass(argument_model, BaseModel)
            or argument_model.model_config.get("strict") is not True
            or argument_model.model_config.get("extra") != "forbid"
        ):
            raise ValueError("argument model must be strict and forbid extras")
        if not (
            inspect.iscoroutinefunction(handler)
            or (callable(handler) and inspect.iscoroutinefunction(handler.__call__))
        ):
            raise ValueError("async cooperative handler required")
        risk = Risk(risk)
        parameters = argument_model.model_json_schema()

        def check_nested_schema(node):
            if isinstance(node, dict):
                if "properties" in node and node.get("additionalProperties") is not False:
                    raise ValueError("nested argument models must forbid extras")
                # Exact admission needs both renderers to agree; Ollama renders these
                # constructs differently from the pinned template (observed +6 tokens).
                if _UNCALIBRATED_SCHEMA & node.keys():
                    raise ValueError("schema construct outside calibrated renderer subset")
                for child in node.values():
                    check_nested_schema(child)
            elif isinstance(node, list):
                for child in node:
                    check_nested_schema(child)

        check_nested_schema(parameters)
        if risk == Risk.ARBITRARY and not {
            "executable",
            "argv",
            "cwd",
            "declared_effects",
        }.issubset(parameters.get("required", [])):
            raise ValueError("arbitrary execution requires reviewable exact arguments")
        schema = {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": parameters},
        }
        self._tools[name] = _Tool(
            name, description, argument_model, handler, capability, risk, schema
        )

    def catalog(self) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "capability": tool.capability,
                "risk": tool.risk.value,
            }
            for tool in self._tools.values()
        ]

    def schemas(self, context: ExecutionContext) -> list[dict]:
        result = []
        for tool in self._tools.values():
            try:
                self.control.check(context, tool.capability)
            except ControlError:
                continue
            result.append(copy.deepcopy(tool.schema))
        return result

    async def execute(
        self, call: ToolCall, context: ExecutionContext, *, cancel: asyncio.Event | None = None
    ) -> ToolResult:
        start = time.monotonic()
        operation = None
        invalid_fields = None
        unknown = False
        task = None

        def result(status, code=None, content=None, *, uncertain=False, outcome=None):
            return ToolResult(
                call_id=call.id,
                name=call.name,
                status=status,
                content=content if content is not None else {},
                error_code=code,
                duration_ms=(time.monotonic() - start) * 1000,
                outcome_unknown=uncertain,
                truncated=outcome.truncated if outcome else False,
                side_effects=tuple(
                    {**effect.model_dump(mode="json"), "operation_id": operation}
                    for effect in outcome.side_effects
                )
                if outcome
                else (),
            )

        try:
            self.control.check(context)
            if cancel is not None and cancel is not context.cancel:
                raise ControlError("cancel_mismatch")
            if (call.turn_id is not None and call.turn_id != context.turn_id) or (
                call.task_id is not None and call.task_id != context.task_id
            ):
                raise ControlError("origin_mismatch")
            tool = self._tools.get(call.name)
            if tool is None:
                raise ControlError("unknown_tool")
            self.control.check(context, tool.capability)
            # Snapshot before await; mutable model arguments cannot change approved action.
            raw = copy.deepcopy(call.arguments)
            try:
                arguments_digest(raw)
                args = tool.model.model_validate(raw, strict=True)
            except ValidationError as exc:
                # Field locations and fixed error types only; never echo input values.
                invalid_fields = [
                    {"field": ".".join(map(str, error["loc"]))[:64], "error": error["type"]}
                    for error in exc.errors(include_url=False, include_input=False)[:8]
                ]
                raise ControlError("invalid_arguments") from None
            except (ValueError, TypeError, OverflowError):
                raise ControlError("invalid_arguments") from None
            call = call.model_copy(
                update={"arguments": raw, "turn_id": context.turn_id, "task_id": context.task_id}
            )
            operation, state = self.control.prepare(
                context,
                call,
                tool.capability,
                tool.risk == Risk.ARBITRARY,
                approval_required=tool.risk == Risk.DESTRUCTIVE,
            )
            if state == "approval_pending":
                return result(state, content={"operation_id": operation})
            deadline = min(context.deadline, start + self.timeout_s)
            guard = EffectGuard(self.control, context, tool.capability, operation, deadline)

            async def invoke():
                guard.check()
                return await tool.handler(args, guard)

            task = asyncio.create_task(invoke())
            cancelled = asyncio.create_task(context.cancel.wait())
            try:
                done, _ = await asyncio.wait(
                    {task, cancelled},
                    timeout=max(0, deadline - time.monotonic()),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if context.cancel.is_set():
                    raise ControlError("cancelled")
                if task not in done or time.monotonic() >= deadline:
                    raise ControlError("deadline_exceeded")
                try:
                    returned = task.result()
                    outcome = validated_outcome(returned)
                except (ValidationError, ValueError, TypeError, OverflowError, RecursionError):
                    raise ControlError("invalid_handler_outcome") from None
                guard.check()
                reply = result(
                    outcome.status,
                    outcome.error_code,
                    outcome.content,
                    uncertain=outcome.status == "unknown",
                    outcome=outcome,
                )
            finally:
                for pending in (task, cancelled):
                    if not pending.done():
                        pending.cancel()
                await asyncio.gather(task, cancelled, return_exceptions=True)
            guard.check()
            if not self.control.finish(operation, outcome.status, outcome.error_code):
                raise ControlError("operation_not_active")
            return reply
        except asyncio.CancelledError:
            if operation:
                self.control.finish(operation, "unknown", "cancelled")
            raise
        except ControlError as exc:
            if operation:
                unknown = True
                self.control.finish(operation, "unknown", exc.code)
            elif exc.code == "replay_blocked":
                try:
                    prior = self.control.operation(context, call)
                    unknown = prior is not None and prior["state"] in ("unknown", "started")
                except ControlError:
                    unknown = True
            evidence = None
            if operation and exc.code in ("cancelled", "deadline_exceeded") and task is not None:
                # Cooperative cleanup may return bounded evidence after interruption.
                # It can never turn timeout/cancel into success or authorize new effects.
                try:
                    try:
                        self.control.check(context, tool.capability)
                    except ControlError as current:
                        if current.code not in ("cancelled", "deadline_exceeded"):
                            raise
                    if task.done() and not task.cancelled() and task.exception() is None:
                        evidence = validated_outcome(task.result())
                except (
                    ControlError,
                    ValidationError,
                    ValueError,
                    TypeError,
                    OverflowError,
                    RecursionError,
                ):
                    evidence = None
            return result(
                "unknown" if unknown else "denied",
                exc.code,
                evidence.content
                if evidence
                else {"invalid_fields": invalid_fields}
                if invalid_fields
                else None,
                uncertain=unknown,
                outcome=evidence,
            )
        except Exception:
            if operation:
                self.control.finish(operation, "unknown", "handler_failed")
                unknown = True
            return result("unknown" if unknown else "failed", "handler_failed", uncertain=unknown)
