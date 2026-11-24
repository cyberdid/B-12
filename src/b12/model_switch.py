"""Between-turn model switching (ADR-023): a local Ollama model with a profile, or a CLI.

The owner switches through the control path (API → here), never through model text. A switch waits
for the agent's model lock, so a running turn finishes on the model it started with. Local models
are listed only when a calibrated profile and its tokenizer exist; a cloud model is the full Capri
(same session, memory and tools) with the large context decided for cloud models on 18.11.2026.
"""

from __future__ import annotations

import asyncio
import json
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

    async def catalog(self) -> list[ModelChoice]:
        local = self.local_choices()
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
            model = OllamaModel(settings)
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

    async def switch(self, choice_id: str) -> ModelChoice:
        choice = await self._choice(choice_id)
        async with self.runtime.agent.model_lock:
            self._apply(choice)
        if choice.kind == "local":
            if self._warm is not None and not self._warm.done():
                self._warm.cancel()
            self._warm = asyncio.create_task(self.warm_up(choice))
        else:
            self._set("ready" if self.which(choice.backend) else "unavailable")
        return choice

    def restore(self) -> None:
        """Re-apply the owner's last choice at start-up (no turn can run yet)."""
        saved = self.runtime.control.get_meta("active_model")
        if not saved or saved == self.active_id:
            return
        for choice in self.local_choices() + [c for c in CLOUD if self.which(c.backend)]:
            if choice.id == saved:
                self._apply(choice)
                return

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
                self._set("loading", detail="завантаження у відеопам'ять")
                response = await client.post(
                    "api/generate", json={"model": choice.model, "prompt": "", "keep_alive": "30m"}
                )
                if response.status_code != 200:
                    raise RuntimeError(f"Ollama HTTP {response.status_code}")
            self._set("ready")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # shown to the owner, never raised into a turn
            self._set("error", detail=str(exc)[:200])

    async def status(self) -> dict:
        status = {"id": self.active_id, **self._status, "elapsed_s": None, "vram_mb": None}
        if self._started is not None and status["state"] in ("loading", "pulling"):
            status["elapsed_s"] = round(time.monotonic() - self._started, 1)
        if self.active_id.startswith("local:") and status["state"] == "ready":
            model = self.active_id.split(":", 1)[1]
            try:
                async with self._client() as client:
                    running = (await client.get("api/ps")).json().get("models", [])
                for item in running:
                    if item.get("name") == model or item.get("model") == model:
                        status["vram_mb"] = int(item.get("size_vram", 0)) // (1024 * 1024)
            except (httpx.HTTPError, ValueError):
                pass
        return status
