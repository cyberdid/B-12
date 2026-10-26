"""Native Ollama streaming with immutable admission and cooperative cancellation.

chat accepts only AdmittedRequest, never late messages/tools/options. on_delta is
(str) -> Awaitable[None]; only async functions/callables are accepted.
Callbacks must remain cooperative/nonblocking and propagate cancellation. asyncio.Event and
an absolute time.monotonic() deadline cover connection, reads and callbacks.
Task.cancel() propagates CancelledError after closing transport. Callbacks are
provisional until ModelReply: a later protocol/budget error cannot retract text.

No conversation or HTTP cache is kept here. Closing a stream cancels this request,
but does NOT certify erasure of the external provider's KV cache. Ollama unloading
is process/model scoped and is deliberately not claimed as a per-actor purge.
"""

import asyncio
import inspect
import json
import math
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

import httpx
from pydantic import ValidationError

from b12.config import Settings
from b12.context import AdmittedRequest
from b12.contracts import ModelReply, ToolCall, _json_value
from b12.model_errors import ModelError as ModelError
from b12.model_profile import ModelProfile, canonical, sha256

DeltaCallback = Callable[[str], Awaitable[None]]
_MAX_WIRE_BYTES = 8 * 1024 * 1024
_MAX_LINE_BYTES = 1024 * 1024
_METRICS = {
    "total_duration",
    "load_duration",
    "prompt_eval_count",
    "prompt_eval_duration",
    "prompt_eval_cached_count",
    "eval_count",
    "eval_duration",
}


class _PublicText:
    """Hold delimiter prefixes across chunks; never buffer hidden reasoning itself."""

    def __init__(self, enabled: bool):
        self.enabled, self.hidden, self.pending = enabled, False, ""

    def feed(self, text: str) -> str:
        if not self.enabled:
            return text
        self.pending += text
        output = []
        while self.pending:
            marker = "</think>" if self.hidden else "<think>"
            index = self.pending.find(marker)
            if index >= 0:
                if not self.hidden:
                    output.append(self.pending[:index])
                self.pending = self.pending[index + len(marker) :]
                self.hidden = not self.hidden
                continue
            keep = next(
                (n for n in range(len(marker) - 1, 0, -1) if self.pending.endswith(marker[:n])), 0
            )
            safe = self.pending[:-keep] if keep else self.pending
            if not self.hidden:
                output.append(safe)
            self.pending = self.pending[-keep:] if keep else ""
            break
        return "".join(output)

    def finish(self) -> str:
        if self.hidden or self.pending:
            # A partial opener is ambiguous. Fail closed instead of leaking its suffix.
            raise ModelError("unterminated_reasoning", "incomplete reasoning delimiter")
        return ""


class _Calls:
    """Native object arguments are merged by index/id, never interpreted as JSON fragments."""

    def __init__(self):
        self.calls: dict[tuple, dict] = {}
        self.response_id = uuid4().hex

    def add(self, calls):
        try:
            if not isinstance(calls, list):
                raise ValueError()
            for call in calls:
                function = call["function"]
                name, arguments = function["name"], function["arguments"]
                _json_value(arguments)
                if not isinstance(arguments, dict):
                    raise ValueError()
                provider_id = call.get("id")
                index = function.get("index")
                if index is not None and (type(index) is not int or index < 0):
                    raise ValueError()
                if provider_id is not None and (
                    not isinstance(provider_id, str) or not provider_id
                ):
                    raise ValueError()
                key = (
                    ("index", index)
                    if index is not None
                    else ("id", provider_id)
                    if provider_id is not None
                    else ("new", len(self.calls))
                )
                current = self.calls.get(key)
                if current is None:
                    current = {
                        "id": provider_id or f"call-{self.response_id}-{len(self.calls)}",
                        "name": name,
                        "arguments": {},
                        "provider_id": provider_id,
                    }
                    self.calls[key] = current
                if current["name"] != name:
                    raise ValueError()
                if provider_id:
                    if current["provider_id"] and current["provider_id"] != provider_id:
                        raise ValueError()
                    current["id"] = current["provider_id"] = provider_id
                for arg, value in arguments.items():
                    if arg in current["arguments"] and current["arguments"][arg] != value:
                        raise ValueError()
                    current["arguments"][arg] = value
                ToolCall(**{k: v for k, v in current.items() if k != "provider_id"})
                ids = [item["id"] for item in self.calls.values()]
                if len(set(ids)) != len(ids) or len(ids) > 128:
                    raise ValueError()
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise ModelError("invalid_tool_call", "invalid native tool call") from exc

    def finish(self) -> tuple[ToolCall, ...]:
        return tuple(
            ToolCall(**{k: v for k, v in call.items() if k != "provider_id"})
            for call in self.calls.values()
        )


def _check_cancel(cancel: asyncio.Event | None, deadline: float) -> None:
    if cancel is not None and cancel.is_set():
        raise ModelError("cancelled", "request cancelled")
    if time.monotonic() >= deadline:
        raise ModelError("deadline_exceeded", "request deadline elapsed")


class OllamaModel:
    def __init__(self, settings: Settings):
        self.settings = settings.model_copy(deep=True)

    async def chat(
        self,
        request: AdmittedRequest,
        *,
        on_delta: DeltaCallback | None = None,
        cancel: asyncio.Event | None = None,
        deadline: float | None = None,
    ) -> ModelReply:
        if on_delta is not None and not (
            inspect.iscoroutinefunction(on_delta)
            or (callable(on_delta) and inspect.iscoroutinefunction(on_delta.__call__))
        ):
            raise ModelError("invalid_callback", "on_delta must be an async callable")
        if cancel is not None and cancel.is_set():
            raise ModelError("cancelled", "request cancelled")
        now = time.monotonic()
        if deadline is not None and (not math.isfinite(deadline) or deadline <= now):
            raise ModelError("deadline_exceeded", "request deadline elapsed")
        deadline = min(deadline or math.inf, now + self.settings.model_timeout_s)
        operation = asyncio.create_task(self._chat(request, on_delta, cancel, deadline))
        cancellation = asyncio.create_task(cancel.wait()) if cancel is not None else None
        tasks = [operation] + ([cancellation] if cancellation is not None else [])
        try:
            finished, _ = await asyncio.wait(
                tasks,
                timeout=max(0, deadline - time.monotonic()),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancellation is not None and cancellation in finished:
                raise ModelError("cancelled", "request cancelled")
            if operation not in finished:
                raise ModelError("deadline_exceeded", "request deadline elapsed")
            result = operation.result()
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        _check_cancel(cancel, deadline)
        return result

    async def _chat(
        self,
        request: AdmittedRequest,
        on_delta: DeltaCallback | None,
        cancel: asyncio.Event | None,
        deadline: float,
    ) -> ModelReply:
        started = time.monotonic()
        # Loading/hash checks are bounded local work, off the event loop for cancellation.
        profile = await asyncio.to_thread(ModelProfile, self.settings)
        if not isinstance(request, AdmittedRequest):
            raise ModelError("admission_invalid", "an admitted snapshot is required")
        await asyncio.to_thread(request.validate, profile)
        if (
            request.num_ctx != self.settings.num_ctx
            or request.output_reserve != self.settings.output_tokens
        ):
            raise ModelError("admission_invalid", "settings changed after admission")
        _check_cancel(cancel, deadline)
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.ollama_url.rstrip("/") + "/",
                timeout=self.settings.model_timeout_s,
                trust_env=False,
            ) as client:
                await self._check_deployment(client, profile)
                async with client.stream(
                    "POST",
                    "api/chat",
                    content=canonical(request.payload()),
                    headers={"Content-Type": "application/json"},
                ) as response:
                    if response.status_code != 200:
                        raise ModelError(
                            "http_error", f"provider HTTP status {response.status_code}"
                        )
                    text_filter = _PublicText(bool(profile.spec.inline_reasoning))
                    calls, content, metrics, first = _Calls(), [], {}, None
                    async for item in self._objects(response):
                        _check_cancel(cancel, deadline)
                        if "error" in item:
                            raise ModelError("provider_error", "provider reported an error")
                        if type(item.get("done")) is not bool:
                            raise ModelError("invalid_terminal", "done must be a boolean")
                        message = item.get("message", {})
                        if not isinstance(message, dict) or not isinstance(
                            message.get("content", ""), str
                        ):
                            raise ModelError("malformed_ndjson", "invalid message")
                        # Never read or copy message.thinking, even into metrics/errors.
                        public = text_filter.feed(message.get("content", ""))
                        if public:
                            visible = "".join(content) + public
                            if (
                                len(profile.tokenizer.encode(visible, add_special_tokens=False).ids)
                                > request.output_reserve
                            ):
                                raise ModelError(
                                    "output_limit", "public text exceeds output reserve"
                                )
                            first = first if first is not None else time.monotonic() - started
                            content.append(public)
                            if on_delta is not None:
                                _check_cancel(cancel, deadline)
                                try:
                                    await on_delta(public)
                                except Exception as exc:
                                    raise ModelError(
                                        "callback_error", "delta callback failed"
                                    ) from exc
                        if "tool_calls" in message:
                            calls.add(message["tool_calls"])
                        if item["done"]:
                            text_filter.finish()
                            for key in _METRICS & item.keys():
                                value = item[key]
                                if type(value) is not int or value < 0:
                                    raise ModelError(
                                        "invalid_terminal", "invalid token/duration metrics"
                                    )
                                metrics[key] = value
                            if (
                                "prompt_eval_count" not in metrics
                                or "eval_count" not in metrics
                                or type(item.get("done_reason")) is not str
                                or item["done_reason"] not in {"stop", "length"}
                            ):
                                raise ModelError("invalid_terminal", "missing terminal metadata")
                            if metrics["prompt_eval_count"] != request.input_tokens:
                                raise ModelError(
                                    "context_mismatch",
                                    "provider prompt count differs from admission",
                                )
                            if metrics["eval_count"] > request.output_reserve:
                                raise ModelError("output_limit", "provider exceeded output reserve")
                            metrics.update(ttft_s=first, elapsed_s=time.monotonic() - started)
                            _check_cancel(cancel, deadline)
                            return ModelReply(
                                content="".join(content),
                                tool_calls=calls.finish(),
                                metrics=metrics,
                                finish_reason=item["done_reason"],
                            )
                    raise ModelError("missing_done", "stream ended without terminal event")
        except httpx.TimeoutException as exc:
            raise ModelError("transport_timeout", "provider transport timed out") from exc
        except httpx.HTTPError as exc:
            raise ModelError("transport_error", "provider transport failed") from exc

    @staticmethod
    async def _check_deployment(client: httpx.AsyncClient, profile: ModelProfile):
        async def read(method, path, **kwargs):
            response = await client.request(method, path, **kwargs)
            if response.status_code != 200:
                raise ModelError("http_error", f"profile HTTP status {response.status_code}")
            try:
                return response.json()
            except ValueError as exc:
                raise ModelError("profile_mismatch", "invalid deployment metadata") from exc

        version = await read("GET", "api/version")
        tags = await read("GET", "api/tags")
        show = await read("POST", "api/show", json={"model": profile.spec.model})
        try:
            matches = [model for model in tags["models"] if model["name"] == profile.spec.model]
            valid = (
                version["version"] == profile.spec.server_version
                and len(matches) == 1
                and matches[0]["digest"] == profile.spec.manifest_digest
                and sha256(show["template"].encode()) == profile.spec.native_template_sha256
            )
        except (TypeError, KeyError, AttributeError):
            valid = False
        if not valid:
            raise ModelError("profile_mismatch", "deployment differs from calibrated profile")

    @staticmethod
    async def _objects(response: httpx.Response):
        pending, total = b"", 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > _MAX_WIRE_BYTES:
                raise ModelError("output_limit", "wire response exceeds safety limit")
            pending += chunk
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                if len(line) > _MAX_LINE_BYTES:
                    raise ModelError("output_limit", "NDJSON line exceeds safety limit")
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                    _json_value(item)
                    if not isinstance(item, dict):
                        raise ValueError()
                except (ValueError, UnicodeError) as exc:
                    raise ModelError("malformed_ndjson", "invalid NDJSON object") from exc
                yield item
            if len(pending) > _MAX_LINE_BYTES:
                raise ModelError("output_limit", "NDJSON fragment exceeds safety limit")
        if pending.strip():
            raise ModelError("malformed_ndjson", "unterminated NDJSON fragment")
