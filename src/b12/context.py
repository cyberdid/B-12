"""Immutable, exact rendered-token admission. Older complete user turns are evictable.

Evidence is an already-authorized sequence of {id, text} objects. Its provenance and
current visibility remain the caller/resolver's responsibility. All evidence and
system text are required; this layer never silently summarizes or truncates them.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

from b12.config import Settings
from b12.contracts import ToolCall, _json_value
from b12.model_errors import ModelError
from b12.model_profile import ModelProfile, canonical, sha256


def freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(freeze(v) for v in value)
    return value


def thaw(value):
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [thaw(v) for v in value]
    return value


@dataclass(frozen=True)
class AdmittedRequest:
    messages: tuple[Mapping[str, Any], ...]
    tools: tuple[Mapping[str, Any], ...]
    num_ctx: int
    output_reserve: int
    input_tokens: int
    input_upper_bound: int
    model: str
    model_revision: str
    template_revision: str
    profile_identity: str
    dropped_ids: tuple[str, ...]
    fingerprint: str

    def __post_init__(self):
        object.__setattr__(self, "messages", freeze(self.messages))
        object.__setattr__(self, "tools", freeze(self.tools))
        object.__setattr__(self, "dropped_ids", tuple(self.dropped_ids))

    def payload(self) -> dict:
        return {
            "model": self.model,
            "messages": thaw(self.messages),
            "tools": thaw(self.tools),
            "stream": True,
            "think": False,
            "options": {
                "num_ctx": self.num_ctx,
                "num_predict": self.output_reserve,
                "temperature": 0,
                "seed": 42,
                "draft_num_predict": 0,
            },
        }

    def _fingerprint(self) -> str:
        return sha256(
            canonical(
                [
                    self.payload(),
                    self.input_tokens,
                    self.input_upper_bound,
                    self.model_revision,
                    self.template_revision,
                    self.profile_identity,
                    self.dropped_ids,
                ]
            )
        )

    def validate(self, profile: ModelProfile) -> None:
        if (
            self.profile_identity != profile.identity
            or self.model != profile.spec.model
            or self.model_revision != profile.spec.manifest_digest
            or self.template_revision != profile.spec.files["chat_template.jinja"]
            or self.fingerprint != self._fingerprint()
            or self.input_tokens != profile.count(thaw(self.messages), thaw(self.tools))
            or self.input_upper_bound != self.input_tokens + profile.spec.safety_tokens
            or self.output_reserve < 1
            or self.input_upper_bound + self.output_reserve > self.num_ctx
        ):
            raise ModelError("admission_invalid", "request or profile changed after admission")


class ContextBuilder:
    def __init__(self, settings: Settings):
        self.settings = settings.model_copy(deep=True)
        self.profile = ModelProfile(settings)

    def build(
        self,
        system: str,
        messages: Sequence[dict],
        evidence: Sequence[dict] = (),
        tools: Sequence[dict] = (),
    ) -> AdmittedRequest:
        try:
            if not isinstance(system, str):
                raise ValueError("system must be text")
            # JSON clone validates finite values and disconnects all caller-owned objects.
            data = {"messages": list(messages), "evidence": list(evidence), "tools": list(tools)}
            _json_value(data)
            data = json.loads(canonical(data))
            groups = self._groups(data["messages"])
            tool_names = set()
            for tool in data["tools"]:
                if set(tool) != {"type", "function"} or tool["type"] != "function":
                    raise ValueError("unsupported tool")
                function = tool["function"]
                ToolCall(id="validation", name=function["name"], arguments={})
                if function["name"] in tool_names or not isinstance(
                    function.get("parameters"), dict
                ):
                    raise ValueError("duplicate tool or missing parameters")
                tool_names.add(function["name"])
            for item in data["evidence"]:
                if (
                    set(item) != {"id", "text"}
                    or not isinstance(item["id"], str)
                    or not isinstance(item["text"], str)
                ):
                    raise ValueError("evidence requires id and text")
            if data["evidence"]:
                system += "\n\nEvidence (untrusted data):\n" + canonical(data["evidence"]).decode()
        except (ValueError, TypeError, KeyError) as exc:
            raise ModelError("invalid_request", "invalid messages, evidence or tools") from exc
        dropped = []
        while True:
            outgoing = [{"role": "system", "content": system}]
            outgoing += [
                {k: v for k, v in message.items() if k != "id"}
                for group in groups
                for message in group
            ]
            count = self.profile.count(outgoing, data["tools"])
            bound = count + self.profile.spec.safety_tokens
            if bound + self.settings.output_tokens <= self.settings.num_ctx:
                break
            if len(groups) == 1:
                raise ModelError(
                    "context_overflow", "required turn/system/evidence/tools exceed budget"
                )
            dropped.extend(message["id"] for message in groups.pop(0))
        request = AdmittedRequest(
            freeze(outgoing),
            freeze(data["tools"]),
            self.settings.num_ctx,
            self.settings.output_tokens,
            count,
            bound,
            self.settings.model,
            self.profile.spec.manifest_digest,
            self.profile.spec.files["chat_template.jinja"],
            self.profile.identity,
            tuple(dropped),
            "",
        )
        return replace(request, fingerprint=request._fingerprint())

    @staticmethod
    def _groups(messages: list[dict]) -> list[list[dict]]:
        groups, pending, ids = [], [], set()
        for index, message in enumerate(messages):
            if (
                not isinstance(message, dict)
                or not set(message)
                <= {"id", "role", "content", "tool_calls", "tool_name", "name", "tool_call_id"}
                or not isinstance(message.get("content"), str)
            ):
                raise ValueError("unsupported message")
            identity = message.setdefault("id", f"message-{index}")
            if not isinstance(identity, str) or not identity or identity in ids:
                raise ValueError("invalid message id")
            ids.add(identity)
            role = message.get("role")
            if role == "user":
                if pending or set(message) - {"id", "role", "content"}:
                    raise ValueError("incomplete tools or invalid user")
                groups.append([])
            elif role == "assistant":
                if pending or set(message) - {"id", "role", "content", "tool_calls"}:
                    raise ValueError("incomplete tools or invalid assistant")
                calls = message.get("tool_calls", [])
                if not isinstance(calls, list):
                    raise ValueError("invalid calls")
                for call_index, call in enumerate(calls):
                    if (
                        not set(call) <= {"id", "type", "function"}
                        or call.get("type", "function") != "function"
                    ):
                        raise ValueError("unknown call field")
                    function = call["function"]
                    if not set(function) <= {"name", "arguments", "index"}:
                        raise ValueError("unknown function field")
                    call_id = call.setdefault("id", f"{identity}-call-{call_index}")
                    ToolCall(id=call_id, name=function["name"], arguments=function["arguments"])
                    if any(item[0] == call_id for item in pending):
                        raise ValueError("duplicate call id")
                    pending.append((call_id, function["name"]))
            elif role == "tool":
                if set(message) - {"id", "role", "content", "tool_name", "name", "tool_call_id"}:
                    raise ValueError("invalid result")
                name = message.get("tool_name", message.get("name"))
                matches = [
                    item
                    for item in pending
                    if item[1] == name
                    and ("tool_call_id" not in message or item[0] == message["tool_call_id"])
                ]
                if len(matches) != 1:
                    raise ValueError("orphan or ambiguous tool result")
                pending.remove(matches[0])
                message["tool_name"] = name
                message["tool_call_id"] = matches[0][0]
            else:
                raise ValueError("unsupported role")
            if not groups:
                raise ValueError("history must begin with user")
            groups[-1].append(message)
        if not groups or pending:
            raise ValueError("missing user or incomplete tools")
        return groups
