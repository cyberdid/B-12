### Task 1: Відтворюваний package, contracts та config

**Files:** Create `pyproject.toml`, `src/b12/__init__.py`, `src/b12/contracts.py`, `src/b12/config.py`, `config.example.toml`, `tests/unit/test_contracts.py`, `tests/unit/test_config.py`. Modify `.gitignore` only for new generated state. Generate `uv.lock`.

**Interfaces produced:**

```python
class Actor(BaseModel):
    schema_version: Literal[1] = 1
    id: str  # 1..128 chars, nonempty after whitespace validation
    owner: bool = False
    consent: bool = False
    # frozen=True; strict=True; extra='forbid'

class MemoryRecord(BaseModel):
    schema_version: Literal[1] = 1
    id: str; owner_id: str; kind: str; text: str
    source: str; created_at: str; evidence_ids: tuple[str, ...] = ()

class ToolCall(BaseModel):
    schema_version: Literal[1] = 1
    id: str; name: str; arguments: dict[str, Any]
    turn_id: str | None = None; task_id: str | None = None

class ToolResult(BaseModel):
    schema_version: Literal[1] = 1
    call_id: str; name: str; status: str
    content: dict[str, Any]; duration_ms: float = 0
    error_code: str | None = None; truncated: bool = False
    side_effects: tuple[dict[str, Any], ...] = (); outcome_unknown: bool = False

class ModelReply(BaseModel):
    schema_version: Literal[1] = 1
    content: str = ''; tool_calls: tuple[ToolCall, ...] = ()
    metrics: dict[str, Any] = {}; finish_reason: str = 'stop'

class Settings(BaseModel):
    state_dir: Path; model: str = 'b12-bolt-e4b:q4km'
    ollama_url: str = 'http://127.0.0.1:11434'
    num_ctx: int = 4096; output_tokens: int = 512
    max_rounds: int = 8; max_tool_calls: int = 16
    tool_timeout_s: float = 30; host_access: str = 'full'
    # validate ranges, loopback URL shape, context reserve, state path
    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> 'Settings': ...
```

MemoryRecord IDs/evidence and non-null ToolCall turn/task IDs are application UUIDs; Actor/provider call IDs are opaque. `created_at` is validated ISO8601 UTC. Actor is a DTO: routes must derive trusted actor/consent from authenticated server state.

- [ ] RED: reject Actor `id=''`, unknown fields and string booleans; reject negative rounds/output reserve >= context, malformed URLs. Confirm no cross-instance mutable defaults.
- [ ] Run `uv run pytest tests/unit/test_contracts.py tests/unit/test_config.py -q`; missing import/validation must fail before production methods exist.
- [ ] Implement strict models/range/path validation and environment parsing; no filesystem writes inside config parsing.
- [ ] GREEN: rerun targeted tests; `uv sync --extra dev --locked` succeeds; package imports without model/GPU.
- [ ] Commit `feat: establish validated B-12 runtime contracts`; review contracts against spec and next tasks.

Example observable test:

```python
def test_text_cannot_turn_into_control_consent():
    with pytest.raises(ValidationError):
        Actor(id='guest', consent='true')
```

