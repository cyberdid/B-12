"""Small local profile: byte-level BPE without merges, no model/download."""

import hashlib
import json

import pytest
from tokenizers import Tokenizer, models, pre_tokenizers

from b12.config import Settings


@pytest.fixture
def profile_settings(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    alphabet = sorted(pre_tokenizers.ByteLevel.alphabet())
    tokenizer = Tokenizer(models.BPE({char: i for i, char in enumerate(alphabet)}, []))
    tokenizer.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False)
    tokenizer.save(str(assets / "tokenizer.json"))
    (assets / "tokenizer_config.json").write_text('{"bos_token":"","eos_token":""}')
    (assets / "chat_template.jinja").write_text(
        "{% for m in messages %}{{m.role}}:{{m.content}}"
        "{{m.tool_calls | default([]) | tojson}};{% endfor %}"
        "{{tools | tojson}}assistant:"
    )
    profile = {
        "renderer": "hf-jinja-v1",
        "revision": "synthetic-v1",
        "model": "test-model",
        "server_version": "test-1",
        "manifest_digest": "a" * 64,
        "native_template_sha256": hashlib.sha256(b"{{ .Prompt }}").hexdigest(),
        "files": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in assets.iterdir()},
        "safety_tokens": 8,
        "inline_reasoning": [["<think>", "</think>"]],
    }
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile))
    return Settings(
        state_dir=tmp_path / "state",
        model="test-model",
        model_profile=path,
        tokenizer_dir=assets,
        num_ctx=256,
        output_tokens=32,
    )
