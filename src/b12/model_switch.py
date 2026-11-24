"""Between-turn model switching (ADR-023): a local Ollama model with a profile, or a CLI.

The owner switches through the control path (API → here), never through model text. A switch waits
for the agent's model lock, so a running turn finishes on the model it started with. Local models
are listed only when a calibrated profile and its tokenizer exist; a cloud model is the full Capri
(same session, memory and tools) with the large context decided for cloud models on 18.11.2026.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx

from b12.cloud_model import CliModel
from b12.context import ContextBuilder
from b12.model import OllamaModel
from b12.model_errors import ModelError

log = logging.getLogger("b12.models")

CLOUD_CONTEXT = {"num_ctx": 200000, "output_tokens": 16384}
_MODEL_FIELDS = ("model", "model_profile", "tokenizer_dir", "num_ctx", "output_tokens")
_LOCAL_GPU_GB = 8  # the owner's laptop GPU; bigger models spill to the CPU


@dataclass(frozen=True)
class ModelChoice:
    id: str
    label: str
    kind: str  # "local" | "cloud"
    backend: str  # "ollama" | "codex" | "claude" | "agy"
    model: str
    location: str  # "ноутбук" | "хмара"
    warning: str = ""

    def as_dict(self) -> dict:
        return dict(self.__dict__)


CLOUD = (
    ModelChoice("codex:gpt-6-luna", "gpt-6-luna · Codex", "cloud", "codex", "gpt-6-luna", "хмара"),
    ModelChoice(
        "claude:claude-opus-5-5", "Claude Opus 5.5", "cloud", "claude", "claude-opus-5-5", "хмара"
    ),
    ModelChoice(
        "claude:claude-sonnet-5-5",
        "Claude Sonnet 5.5",
        "cloud",
        "claude",
        "claude-sonnet-5-5",
        "хмара",
    ),
    ModelChoice("agy:gemini", "Gemini · agy", "cloud", "agy", "", "хмара"),
)


def _size_warning(model: str) -> str:
    match = re.search(r"(\d+(?:\.\d+)?)b\b", model.lower())
    if match and float(match.group(1)) > 14:
        return f"не вміщається у {_LOCAL_GPU_GB} ГБ GPU — частина піде на процесор, буде повільно"
    return ""


class _Gated:
    """A local model still downloading or loading: a turn waits for it, or fails readably."""

    def __init__(self, inner, ready: asyncio.Event, failure: Callable[[], str | None]):
        self.inner, self._ready, self._failure = inner, ready, failure

    async def chat(self, request, *, on_delta=None, cancel=None, deadline=None):
        if not self._ready.is_set():
            timeout = None if deadline is None else max(0.0, deadline - time.monotonic())
            try:
                await asyncio.wait_for(self._ready.wait(), timeout)
            except TimeoutError:
                raise ModelError("deadline_exceeded", "model is still loading") from None
        failure = self._failure()
        if failure:
            raise ModelError("model_unavailable", failure[:200])
        return await self.inner.chat(request, on_delta=on_delta, cancel=cancel, deadline=deadline)

    async def unload(self, **kwargs) -> bool:
        return await self.inner.unload(**kwargs)

    def __getattr__(self, name):
        return getattr(self.inner, name)


class ModelSwitch:
    def __init__(
        self,
        runtime,
        *,
        share: Path | None = None,
        which: Callable[[str], str | None] = shutil.which,
    ):
        self.runtime = runtime
        self.base = runtime.settings
        self.share = share or Path.home() / ".local/share/b12"
        self.which = which
        self.active_id = f"local:{self.base.model}"
        self.previous_id: str | None = None
        self.on_status: Callable[[dict], None] | None = None
        self._status = {"state": "ready", "progress": None, "detail": ""}
        self._started: float | None = None
        self._warm: asyncio.Task | None = None
        self._ready = asyncio.Event()
        self._ready.set()
        self._profiles: dict[str, tuple[Path, Path, str]] = {}

    # ---- catalog ----------------------------------------------------------------
    def local_choices(self) -> list[ModelChoice]:
        """Models with a calibrated profile and tokenizer on disk (not yet checked in Ollama)."""
        paths = sorted((self.share / "profiles").glob("*.json"))
        if self.base.model_profile is not None:
            paths.insert(0, Path(self.base.model_profile))  # the configured one wins duplicates
        found: dict[str, tuple[Path, Path, str]] = {}
        for path in paths:
            try:
                spec = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            model = spec.get("model")
            if not model or model in found:
                continue
            if path == self.base.model_profile and self.base.tokenizer_dir is not None:
                tokenizer = Path(self.base.tokenizer_dir)
            else:
                matches = sorted((self.share / "tokenizers").glob(f"*/{spec.get('revision')}"))
                if not matches:
                    continue
                tokenizer = matches[0]
            found[model] = (path, tokenizer, spec.get("manifest_digest", ""))
        self._profiles = found
        return [
            ModelChoice(f"local:{m}", m, "local", "ollama", m, "ноутбук", _size_warning(m))
            for m in found
        ]

    async def _downloaded(self) -> set[str] | None:
        try:
            async with self._client() as client:
                tags = (await client.get("api/tags")).json().get("models", [])
        except (httpx.HTTPError, ValueError):
            return None  # Ollama not reachable: say nothing rather than guess
        return {t.get("name") for t in tags}

    async def catalog(self) -> list[ModelChoice]:
        local = self.local_choices()
        downloaded = await self._downloaded()
        if downloaded is not None:
            note = "не завантажено: вибір почне завантаження з Ollama"
            local = [
                c
                if c.model in downloaded
                else ModelChoice(
                    **{**c.as_dict(), "warning": "; ".join(filter(None, [note, c.warning]))}
                )
                for c in local
            ]
        return local + [c for c in CLOUD if self.which(c.backend)]

    async def _choice(self, choice_id: str) -> ModelChoice:
        for choice in await self.catalog():
            if choice.id == choice_id:
                return choice
        raise KeyError(choice_id)

    # ---- switching --------------------------------------------------------------
    def _apply(self, choice: ModelChoice) -> None:
        if choice.kind == "local":
            if choice.model not in self._profiles:
                self.local_choices()
            profile, tokenizer, _ = self._profiles[choice.model]
            settings = self.base.model_copy(
                update={"model": choice.model, "model_profile": profile, "tokenizer_dir": tokenizer}
            )
            model = _Gated(OllamaModel(settings), self._ready, self._failure)
        else:
            settings = self.base.model_copy(update=CLOUD_CONTEXT)
            model = CliModel(choice.backend, choice.model)
        builder = ContextBuilder(settings)  # validates the profile before anything changes
        agent = self.runtime.agent
        agent.settings = agent.settings.model_copy(
            update={k: getattr(settings, k) for k in _MODEL_FIELDS}
        )
        agent.builder, agent.model, self.runtime.model = builder, model, model
        if choice.id != self.active_id:
            self.previous_id = self.active_id
        self.active_id = choice.id
        self.runtime.control.set_meta("active_model", choice.id)

    def _failure(self) -> str | None:
        return self._status.get("detail") if self._status.get("state") == "error" else None

    async def switch(self, choice_id: str) -> ModelChoice:
        choice = await self._choice(choice_id)
        if self._warm is not None and not self._warm.done():
            self._warm.cancel()  # an earlier download/load must not report against this model
        self._warm = None
        agent = self.runtime.agent
        async with agent.model_lock:
            old = agent.model
            if choice.kind == "local":
                self._ready.clear()
                self._set("loading", detail="підготовка моделі")
            self._apply(choice)
            # The outgoing local model leaves the GPU with its KV cache (a purge then only has
            # the active model to reset). A turn still running keeps it and Ollama reloads it.
            running = any(
                not key.startswith(("skill_review-", "memory_review-")) for key in agent.active
            )
            if old is not agent.model and not running and hasattr(old, "unload"):
                try:
                    await old.unload(timeout_s=10)
                except (ModelError, OSError) as exc:
                    log.warning("could not unload the previous model: %s", exc)
        if choice.kind == "local":
            self._warm = asyncio.create_task(self.warm_up(choice))
        else:
            self._ready.set()
            self._set("ready" if self.which(choice.backend) else "unavailable")
        return choice

    def restore(self) -> None:
        """Re-apply the owner's last choice at start-up (no turn can run yet)."""
        saved = self.runtime.control.get_meta("active_model")
        if not saved or saved == self.active_id:
            return
        for choice in self.local_choices() + [c for c in CLOUD if self.which(c.backend)]:
            if choice.id == saved:
                try:
                    self._apply(choice)
                except Exception as exc:  # a broken profile must never stop the runtime
                    log.warning("saved model %s cannot be restored: %s", saved, exc)
                    break
                return
        # The saved model is gone or broken: keep the configured one and forget the choice.
        self.runtime.control.set_meta("active_model", "")

    # ---- status -----------------------------------------------------------------
    def _set(self, state: str, **fields) -> None:
        if state in ("loading", "pulling") and self._status.get("state") not in (
            "loading",
            "pulling",
        ):
            self._started = time.monotonic()
        self._status = {"state": state, "progress": None, "detail": "", **fields}
        if self.on_status is not None:
            self.on_status(dict(self._status))

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base.ollama_url.rstrip("/") + "/",
            timeout=httpx.Timeout(30.0, read=None),
            trust_env=False,
        )

    async def warm_up(self, choice: ModelChoice) -> None:
        """Download (when missing) and load a local model, reporting progress."""
        try:
            async with self._client() as client:
                tags = (await client.get("api/tags")).json().get("models", [])
                if not any(t.get("name") == choice.model for t in tags):
                    self._set("pulling", progress=0.0, detail="завантаження моделі")
                    async with client.stream(
                        "POST", "api/pull", json={"model": choice.model, "stream": True}
                    ) as response:
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            item = json.loads(line)
                            if item.get("error"):
                                raise RuntimeError(item["error"])
                            total, done = item.get("total"), item.get("completed")
                            if total and done is not None:
                                self._set(
                                    "pulling",
                                    progress=round(done / total, 3),
                                    detail=item.get("status", ""),
                                )
                expected = self._profiles.get(choice.model, (None, None, ""))[2]
                tags = (await client.get("api/tags")).json().get("models", [])
                digest = next((t.get("digest") for t in tags if t.get("name") == choice.model), "")
                if expected and digest and digest != expected:
                    raise RuntimeError(
                        "версія моделі в Ollama не збігається з каліброваним профілем "
                        f"({digest[:12]} ≠ {expected[:12]})"
                    )
                self._set("loading", detail="завантаження у відеопам'ять")
                # Load with the context the turns use: a different num_ctx makes Ollama reload
                # the model inside the first turn (on the 8 GB laptop GPU that hit the deadline).
                response = await client.post(
                    "api/generate",
                    json={
                        "model": choice.model,
                        "prompt": "",
                        "keep_alive": "30m",
                        "options": {"num_ctx": self.base.num_ctx},
                    },
                )
                if response.status_code != 200:
                    raise RuntimeError(f"Ollama HTTP {response.status_code}")
                # "ready" only once the model is really in memory.
                for _ in range(600):
                    running = (await client.get("api/ps")).json().get("models", [])
                    if any(choice.model in (m.get("name"), m.get("model")) for m in running):
                        break
                    await asyncio.sleep(1.0)
                else:
                    raise RuntimeError("Ollama did not load the model in 10 minutes")
            self._set("ready")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # shown to the owner, never raised into a turn
            self._set("error", detail=str(exc)[:200])
        finally:
            self._ready.set()  # a waiting turn proceeds, or fails with the error above

    async def status(self) -> dict:
        status = {
            "id": self.active_id,
            **self._status,
            "elapsed_s": None,
            "vram_mb": None,
            "cpu_share": None,
        }
        if self._started is not None and status["state"] in ("loading", "pulling"):
            status["elapsed_s"] = round(time.monotonic() - self._started, 1)
        if self.active_id.startswith("local:") and status["state"] == "ready":
            model = self.active_id.split(":", 1)[1]
            try:
                async with self._client() as client:
                    running = (await client.get("api/ps")).json().get("models", [])
                for item in running:
                    if item.get("name") == model or item.get("model") == model:
                        vram, size = int(item.get("size_vram", 0)), int(item.get("size", 0))
                        status["vram_mb"] = vram // (1024 * 1024)
                        if size > vram > 0:  # part of the model runs on the CPU: slow
                            status["cpu_share"] = round(1 - vram / size, 2)
            except (httpx.HTTPError, ValueError):
                pass
        return status
