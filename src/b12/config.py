"""Перевірка runtime configuration без створення стану чи мережевих запитів."""

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", validate_default=True)

    state_dir: Path
    model: str = "b12-bolt-e4b:q4km"
    ollama_url: str = "http://127.0.0.1:11434"
    model_profile: Path | None = None
    tokenizer_dir: Path | None = None
    model_timeout_s: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 120
    num_ctx: Annotated[int, Field(gt=0)] = 4096
    output_tokens: Annotated[int, Field(gt=0)] = 512
    # Sampling. Eval/determinism default is temperature 0; NVIDIA recommends 1.0 / top_p 0.95.
    temperature: Annotated[float, Field(ge=0, le=2, allow_inf_nan=False)] = 0.0
    top_p: Annotated[float, Field(gt=0, le=1, allow_inf_nan=False)] = 1.0
    seed: Annotated[int, Field(ge=0, le=2**31 - 1)] = 42
    # Bytes of one tool result shown to the model before clipping (context budget).
    tool_result_bytes: Annotated[int, Field(ge=512, le=16384)] = 4096
    max_rounds: Annotated[int, Field(gt=0)] = 8
    max_tool_calls: Annotated[int, Field(gt=0)] = 16
    tool_timeout_s: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 30
    host_access: Literal["full", "read_only", "none"] = "full"
    # Owner-chosen wide access. Both are control-channel settings; model output cannot set them.
    # forget_requires_approval=False lets memory_forget run on the owner's grant alone.
    forget_requires_approval: bool = True
    # "approval": sudo_exec is offered to owner tasks, each exact command still needs approval.
    sudo_access: Literal["off", "approval"] = "off"
    # http_fetch destinations: exact hosts, "*.suffix" (subdomains) or "*" (all); empty denies all.
    network_allow: tuple[Annotated[str, Field(min_length=1, max_length=253)], ...] = ()
    # Initiative policy (local wall clock). Quiet hours block nonurgent speech only.
    timezone: str = "Europe/Kyiv"
    quiet_start: Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")] = "23:00"
    quiet_end: Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")] = "08:00"
    initiative_hour_cap: Annotated[int, Field(ge=0, le=60)] = 3
    initiative_cooldown_s: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 600
    scheduler_tick_s: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 60
    # Optional semantic recall: interpreter of an existing embedding app (e.g. the owner's
    # archive-index venv) running scripts/embed_bridge.py. None keeps lexical-only recall.
    embedding_python: str | None = None
    embedding_backend: str = "archive_index.embed:Embedder"

    @field_validator("state_dir", mode="before")
    @classmethod
    def _state_path(cls, value: Any) -> Path:
        if not isinstance(value, str | Path) or not str(value).strip() or "\0" in str(value):
            raise ValueError("state_dir must be a nonempty filesystem path")
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("state_dir must be absolute (or begin with ~)")
        path = path.resolve(strict=False)
        if path == Path(path.anchor) or (path.exists() and not path.is_dir()):
            raise ValueError("state_dir must identify a dedicated directory")
        if any(parent.exists() and not parent.is_dir() for parent in path.parents):
            raise ValueError("state_dir ancestors must be directories")
        return path

    @field_validator("model_profile", "tokenizer_dir", mode="before")
    @classmethod
    def _profile_path(cls, value: Any) -> Path | None:
        if value is None:
            return None
        if not isinstance(value, str | Path) or not str(value).strip():
            raise ValueError("profile paths must be nonempty")
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("profile paths must be absolute")
        return path

    @field_validator("model")
    @classmethod
    def _model_is_nonblank(cls, value: str) -> str:
        if not value.strip() or any(c.isspace() for c in value):
            raise ValueError("model must be a nonblank model identifier without whitespace")
        return value

    @field_validator("ollama_url")
    @classmethod
    def _http_endpoint(cls, value: str) -> str:
        if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value) or "\\" in value:
            raise ValueError("ollama_url contains invalid whitespace or separator")
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or "?" in value
            or "#" in value
            or parsed.netloc.endswith(":")
        ):
            raise ValueError("ollama_url must be an HTTP(S) endpoint without credentials or query")
        # Access validates malformed/non-numeric/out-of-range ports.
        if parsed.port is not None and parsed.port < 1:
            raise ValueError("ollama_url port must be positive")
        hostname = parsed.hostname
        if ":" not in hostname:
            ascii_hostname = hostname.encode("idna").decode("ascii").rstrip(".")
            if len(ascii_hostname) > 253 or not all(
                re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                for label in ascii_hostname.split(".")
            ):
                raise ValueError("ollama_url has a malformed hostname")
        return value

    @model_validator(mode="after")
    def _output_fits_context(self) -> "Settings":
        if self.output_tokens >= self.num_ctx:
            raise ValueError("output_tokens must leave input capacity within num_ctx")
        return self

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        """B12_* values override defaults; the supplied mapping isolates ambient env."""
        env = os.environ if environ is None else environ
        state_home = Path(env.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
        values: dict[str, Any] = {"state_dir": env.get("B12_STATE_DIR", state_home / "b12")}
        integers = {
            "num_ctx",
            "output_tokens",
            "max_rounds",
            "max_tool_calls",
            "initiative_hour_cap",
            "tool_result_bytes",
            "seed",
        }
        for field in cls.model_fields:
            key = f"B12_{field.upper()}"
            if key not in env or field == "state_dir":
                continue
            value: Any = env[key]
            if field in integers:
                value = int(value)
            elif field in ("temperature", "top_p"):
                value = float(value)
            elif field == "network_allow":
                value = tuple(item.strip() for item in value.split(",") if item.strip())
            elif field == "forget_requires_approval":
                value = value.strip().lower() in ("1", "true", "yes", "on")
            elif field in {
                "tool_timeout_s",
                "model_timeout_s",
                "initiative_cooldown_s",
                "scheduler_tick_s",
            }:
                value = float(value)
            values[field] = value
        return cls(**values)
