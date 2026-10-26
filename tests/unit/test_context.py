import json
from dataclasses import replace

import pytest

from b12.context import ContextBuilder
from b12.model import ModelError


def test_required_latest_user_cannot_be_evicted(profile_settings):
    builder = ContextBuilder(profile_settings)
    with pytest.raises(ModelError, match="context_overflow"):
        builder.build("S", [{"role": "user", "content": "ї" * 200}], [], [])


def test_evicts_old_turns_before_fixed_system_evidence_and_latest_user(profile_settings):
    request = ContextBuilder(profile_settings).build(
        "S",
        [
            {"id": "old", "role": "user", "content": "x" * 160},
            {"id": "answer", "role": "assistant", "content": "old answer"},
            {"id": "latest", "role": "user", "content": "нове"},
        ],
        [{"id": "ev", "text": "доказ"}],
        [],
    )
    assert request.dropped_ids == ("old", "answer")
    assert request.messages[-1]["content"] == "нове"
    assert "доказ" in request.messages[0]["content"]
    assert request.input_upper_bound + request.output_reserve <= request.num_ctx


def test_tool_schema_and_complete_serialization_count_towards_admission(profile_settings):
    tool = {
        "type": "function",
        "function": {
            "name": "run",
            "description": "x" * 240,
            "parameters": {"type": "object", "properties": {}},
        },
    }
    with pytest.raises(ModelError, match="context_overflow"):
        ContextBuilder(profile_settings).build("S", [{"role": "user", "content": "hi"}], [], [tool])


def tool_round():
    return [
        {"id": "q", "role": "user", "content": "run"},
        {
            "id": "a",
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "opaque", "type": "function", "function": {"name": "run", "arguments": {}}}
            ],
        },
        {
            "id": "r",
            "role": "tool",
            "tool_call_id": "opaque",
            "tool_name": "run",
            "content": "x" * 200,
        },
    ]


def test_active_tool_round_is_required_and_old_tool_round_evicted_atomically(profile_settings):
    builder = ContextBuilder(profile_settings)
    with pytest.raises(ModelError, match="context_overflow"):
        builder.build("S", tool_round(), [], [])
    request = builder.build(
        "S", tool_round() + [{"id": "new", "role": "user", "content": "ok"}], [], []
    )
    assert request.dropped_ids == ("q", "a", "r")
    assert [m["role"] for m in request.messages] == ["system", "user"]


@pytest.mark.parametrize(
    "messages",
    [
        [
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "orphan", "tool_name": "run"},
        ],
        tool_round()[:-1],
        tool_round()[:-1]
        + [{"role": "tool", "content": "wrong", "tool_call_id": "other", "tool_name": "run"}],
        [{"role": "user", "content": "hi", "images": ["unbudgeted"]}],
    ],
)
def test_invalid_or_unbudgeted_protocol_is_rejected(profile_settings, messages):
    with pytest.raises(ModelError, match="invalid_request"):
        ContextBuilder(profile_settings).build("S", messages, [], [])


def test_snapshot_nested_values_cannot_change_and_input_mutations_do_not_leak(profile_settings):
    profile_settings.num_ctx = 1024
    tools = [{"type": "function", "function": {"name": "run", "parameters": {"type": "object"}}}]
    messages = [{"role": "user", "content": "hi"}]
    request = ContextBuilder(profile_settings).build("S", messages, [], tools)
    messages[0]["content"] = "mutated"
    tools[0]["function"]["name"] = "changed"
    assert request.messages[-1]["content"] == "hi"
    assert request.tools[0]["function"]["name"] == "run"
    with pytest.raises(TypeError):
        request.tools[0]["function"]["name"] = "changed"
    with pytest.raises(ModelError, match="admission_invalid"):
        replace(request, input_upper_bound=0).validate(ContextBuilder(profile_settings).profile)


def test_unknown_or_changed_profile_fails_closed(profile_settings):
    path = profile_settings.model_profile
    value = json.loads(path.read_text())
    value["renderer"] = "unknown"
    path.write_text(json.dumps(value))
    with pytest.raises(ModelError, match="profile_invalid"):
        ContextBuilder(profile_settings)
    value["renderer"] = "hf-jinja-v1"
    path.write_text(json.dumps(value))
    (profile_settings.tokenizer_dir / "chat_template.jinja").write_text("changed")
    with pytest.raises(ModelError, match="profile_invalid"):
        ContextBuilder(profile_settings)


def test_manually_constructed_snapshot_still_freezes_nested_values(profile_settings):
    request = ContextBuilder(profile_settings).build("S", [{"role": "user", "content": "hi"}])
    replaced = replace(request, messages=({"role": "user", "content": "mutable"},))
    with pytest.raises(TypeError):
        replaced.messages[0]["content"] = "changed"


def test_unrecognized_or_mislabelled_history_tool_types_are_rejected(profile_settings):
    messages = tool_round()
    messages[1]["tool_calls"][0]["type"] = "code_execution"
    with pytest.raises(ModelError, match="invalid_request"):
        ContextBuilder(profile_settings).build("S", messages)


def test_exact_budget_boundary_and_one_token_overflow(profile_settings):
    # Byte tokenizer: system:S[];user:hi[];[]assistant: = 33 bytes/tokens.
    profile_settings.num_ctx = 73  # 33 input + 8 margin + 32 output
    request = ContextBuilder(profile_settings).build("S", [{"role": "user", "content": "hi"}])
    assert request.input_tokens == 33
    assert request.input_upper_bound == 41
    with pytest.raises(ModelError, match="context_overflow"):
        ContextBuilder(profile_settings).build("S", [{"role": "user", "content": "hix"}])


@pytest.mark.parametrize(
    "asset,content",
    [
        ("chat_template.jinja", "{% invalid_jinja %}"),
        ("tokenizer.json", '{"invalid":"tokenizer"}'),
    ],
)
def test_invalid_but_hash_consistent_assets_have_structured_failure(
    profile_settings, asset, content
):
    import hashlib

    path = profile_settings.tokenizer_dir / asset
    path.write_text(content)
    profile = json.loads(profile_settings.model_profile.read_text())
    profile["files"][asset] = hashlib.sha256(path.read_bytes()).hexdigest()
    profile_settings.model_profile.write_text(json.dumps(profile))
    with pytest.raises(ModelError, match="profile_invalid"):
        ContextBuilder(profile_settings)


@pytest.mark.parametrize("field", ["model_revision", "template_revision"])
def test_revision_identity_is_checked_even_with_recomputed_fingerprint(profile_settings, field):
    builder = ContextBuilder(profile_settings)
    request = builder.build("S", [{"role": "user", "content": "hi"}])
    changed = replace(request, **{field: "different"})
    changed = replace(changed, fingerprint=changed._fingerprint())
    with pytest.raises(ModelError, match="admission_invalid"):
        changed.validate(builder.profile)


@pytest.mark.parametrize(
    "malformation",
    [
        "images",
        "orphan",
        "incomplete",
        "missing_system",
        "missing_user",
        "tools_schema",
    ],
)
def test_reconstructed_snapshot_cannot_bypass_structural_admission(profile_settings, malformation):
    builder = ContextBuilder(profile_settings)
    request = builder.build("S", [{"role": "user", "content": "hi"}])
    payload = request.payload()
    if malformation == "images":
        payload["messages"][-1]["images"] = ["unbudgeted"]
    elif malformation == "orphan":
        payload["messages"].append({"role": "tool", "tool_name": "run", "content": "result"})
    elif malformation == "incomplete":
        payload["messages"].append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"function": {"name": "run", "arguments": {}}}],
            }
        )
    elif malformation == "missing_system":
        payload["messages"].pop(0)
    elif malformation == "missing_user":
        payload["messages"].pop()
    else:
        payload["tools"] = [{"type": "not_function", "function": {"name": "run"}}]
    # Deliberately defeat the count/hash gates: this regression isolates structural admission.
    count = builder.profile.count(payload["messages"], payload["tools"])
    forged = replace(
        request,
        messages=payload["messages"],
        tools=payload["tools"],
        input_tokens=count,
        input_upper_bound=count + 8,
        num_ctx=1024,
    )
    forged = replace(forged, fingerprint=forged._fingerprint())
    with pytest.raises(ModelError, match="admission_invalid"):
        forged.validate(builder.profile)


@pytest.mark.parametrize(
    "bad_function",
    [
        {"name": "run", "parameters": {}, "unsupported": "unbudgeted"},
        {"name": "run", "description": [], "parameters": {"type": "object"}},
        {"name": "run", "parameters": {"type": "string"}},
        {"name": "run", "parameters": {"type": "object", "properties": []}},
        {"name": "run", "parameters": {"type": "object", "required": "argument"}},
        {"name": "run", "parameters": {"type": "object", "required": ["unknown"]}},
    ],
)
@pytest.mark.parametrize("entrypoint", ["builder", "snapshot"])
def test_tool_schema_validation_is_shared(profile_settings, bad_function, entrypoint):
    profile_settings.num_ctx = 1024
    builder = ContextBuilder(profile_settings)
    tools = [{"type": "function", "function": bad_function}]
    if entrypoint == "builder":
        with pytest.raises(ModelError, match="invalid_request"):
            builder.build("S", [{"role": "user", "content": "hi"}], tools=tools)
    else:
        request = builder.build("S", [{"role": "user", "content": "hi"}])
        count = builder.profile.count(request.payload()["messages"], tools)
        forged = replace(request, tools=tools, input_tokens=count, input_upper_bound=count + 8)
        forged = replace(forged, fingerprint=forged._fingerprint())
        with pytest.raises(ModelError, match="admission_invalid"):
            forged.validate(builder.profile)
