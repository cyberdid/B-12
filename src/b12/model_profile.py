"""Explicit local tokenizer profiles. Never downloads assets or guesses a renderer."""

import hashlib
import json
from typing import Annotated, Literal

from jinja2.sandbox import ImmutableSandboxedEnvironment
from pydantic import BaseModel, ConfigDict, Field
from tokenizers import Tokenizer

from b12.config import Settings
from b12.model_errors import ModelError


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class ProfileSpec(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    renderer: Literal["hf-jinja-v1"]
    revision: Annotated[str, Field(min_length=1)]
    model: str
    server_version: str
    manifest_digest: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    native_template_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    files: dict[str, str]
    safety_tokens: Annotated[int, Field(ge=0, le=1024)]
    inline_reasoning: list[list[str]]


class ModelProfile:
    def __init__(self, settings: Settings):
        try:
            if settings.model_profile is None or settings.tokenizer_dir is None:
                raise ValueError("explicit profile and assets required")
            self.spec = ProfileSpec.model_validate_json(settings.model_profile.read_bytes())
            if self.spec.model != settings.model:
                raise ValueError("model differs")
            names = {"tokenizer.json", "tokenizer_config.json", "chat_template.jinja"}
            if set(self.spec.files) != names:
                raise ValueError("incomplete profile")
            # Read once; hash and parse exactly those bytes to avoid asset TOCTOU.
            assets = {name: (settings.tokenizer_dir / name).read_bytes() for name in names}
            if any(sha256(data) != self.spec.files[name] for name, data in assets.items()):
                raise ValueError("asset hash mismatch")
            if self.spec.inline_reasoning not in ([], [["<think>", "</think>"]]):
                raise ValueError("unsupported reasoning delimiters")
            self.identity = sha256(canonical(self.spec.model_dump()))
            self.tokenizer = Tokenizer.from_str(assets["tokenizer.json"].decode())
            # Never let a tokenizer's saved truncation/padding silently change the count.
            self.tokenizer.no_truncation()
            self.tokenizer.no_padding()
            config = json.loads(assets["tokenizer_config.json"])
            self.special_tokens = {key: config[key] for key in ("bos_token", "eos_token")}
            env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)

            def raise_exception(message):
                raise ValueError("template rejected input")

            env.globals["raise_exception"] = raise_exception
            self.template = env.from_string(assets["chat_template.jinja"].decode())
        except Exception as exc:
            # tokenizers exposes parse errors as the base Exception class.
            raise ModelError(
                "profile_invalid", "missing, unsupported or mismatched profile"
            ) from exc

    def count(self, messages: list[dict], tools: list[dict]) -> int:
        try:
            rendered = self.template.render(
                messages=messages,
                tools=tools,
                add_generation_prompt=True,
                enable_thinking=False,
                conversational_mode=False,
                **self.special_tokens,
            )
            return len(self.tokenizer.encode(rendered, add_special_tokens=False).ids)
        except Exception as exc:
            raise ModelError("invalid_request", "profile cannot render request") from exc
