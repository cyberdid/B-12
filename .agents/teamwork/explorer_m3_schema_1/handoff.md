# Handoff Report: Scenario Schema & Runner Architecture (Milestone M3)

**Author:** Explorer 1 (Schema & Runner Architecture)  
**Date:** 2026-11-10  
**Target:** Milestone M3 Scenario Authoring & Validation  
**Deliverable Path:** `/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m3_schema_1/handoff.md`

---

## 1. Observation

This investigation conducted a code-level audit of the Capri Comprehensive Evaluation schema models, execution engines, deterministic evaluators, and reference specifications.

### 1.1 Direct Source Observations

1. **`evals/capri_comprehensive/evaluators/schema.py`**:
   - Implements Pydantic V2 models:
     - `ScenarioDefinition`: Root scenario model with ID regex `^([A-Z]{2,4}-[0-9]{2}|(Journey|JOURNEY)-[0-9]{1,2})$`.
     - `PreConditions`: Encapsulates `runtime_settings: RuntimeSettings` and `initial_state: InitialState`.
     - `RuntimeSettings`: Fields `num_ctx: int = 4096` (bounded `512 <= num_ctx <= 32768`), `temperature: float = 0.0` (bounded `0.0 <= temp <= 2.0`), `model: str = "pinned_primary"`, `seed: int | None = 42`.
     - `InitialState`: `actors: list[ActorSpec] = []`, `memories: list[MemorySpec] = []`, `preferences: list[PreferenceSpec] = []`, `files: dict[str, str] = {}`, `mock_services: list[MockServiceSpec] = []`.
     - `ActorSpec`: `id: str = "actor-owner-01"`, `owner: bool = True`, `consent: bool = True`, `display_name: str | None = None`.
     - `MemorySpec`: `text: str` (REQUIRED), `actor_id: str = "actor-owner-01"`, `timestamp: str = "2026-10-24T14:00:00Z"`, `tier: str | None = "autobiographical"`, `provenance: str | None = "direct_conversation"`.
     - `PreferenceSpec`: `key: str` (REQUIRED), `value: str` (REQUIRED), `actor_id: str = "actor-owner-01"`.
     - `MockServiceSpec`: `name: str` (REQUIRED), `endpoint: str` (REQUIRED), `response: Any = None`, `status_code: int = 200`.
     - `InteractionTurn`: `turn: int = 0`, `actor_id: str = "actor-owner-01"`, `input: str` (REQUIRED, `min_length=1`), `new_session: bool = False`, `expected_behaviors: list[EvaluationRule] = []`, `forbidden_behaviors: list[EvaluationRule] = []`.
     - `EvaluationRule`: Model defining rule assertions for both expected and forbidden behaviors. Fields: `type: str` (REQUIRED), `value: Any | None = None`, `values: list[Any] = []`, `name: str | None = None`, `names: list[str] = []`, `path: str | None = None`, `ignore_case: bool = True`, `turn: int | None = None`, `threshold_ms: float | None = None`, `pattern: str | None = None`.
     - `GroundTruth`: `reference_answer: str | None = None`, `evidence_criteria: str | None = None`, `target_metrics: TargetMetrics` (`ttft_s_max`, `total_latency_s_max`, `max_memory_mb`).
     - `EvaluationConfig`: `method: str = "deterministic_rule"` (`deterministic_rule` | `frozen_broker_judge` | `trace_diff`), `pass_criteria: str`, `failure_criteria: str | None = None`, `judge_model: str | None = None`, `judge_rubric: str | None = None`.
     - `required_artifacts: list[str] = []` on `ScenarioDefinition`.
     - `metadata: dict[str, Any] = {}` on `ScenarioDefinition`.

2. **`evals/capri_comprehensive/runners/runner.py`**:
   - `ScenarioRunner.run()`:
     - Directly checks `scenario.execution_mode`. If `BLOCKED_HARDWARE`, immediately records `ExecutionStatus.BLOCKED_HARDWARE`, `raw_score = 0.0`, and outputs `blocker_reason = f"Missing physical hardware requirement: {scenario.hardware_prereq}"` without invoking models or sandboxes.
     - If `BLOCKED_DELAY`, records `ExecutionStatus.BLOCKED_DELAY`, `raw_score = 0.0`, and outputs `blocker_reason = "Multi-day longitudinal wall-clock delay required (Long-Term Protocol)"`.
     - For runnable scenarios (`automated_immediate`, `simulated_time`), enters `SandboxedEnvironment(scenario_id, initial_files)`.
     - Seeds `world_state`: `sandbox_dir`, `workspace_dir`, `memories` (list of texts), `memory_count`, `actors`, `preferences`, `exit_code = 0`.
     - Iterates through `scenario.interactions`, measures TTFT and total duration, dispatches turns to `turn_executor` (or local Ollama API `/api/chat`), and calls `evaluate_turn_rules()`.
     - Automatically generates artifacts: `execution_report.json`, `turn_trace.jsonl`, `latencies.json`.

3. **`evals/capri_comprehensive/evaluators/deterministic.py`**:
   - `evaluate_single_rule()` handles 18 distinct evaluator types and aliases:
     - Exact string: `content_exact`, `exact_string`
     - Substring match: `content_contains`, `substring`
     - Substring omission: `content_not_contains`
     - Multi-substring match (OR): `content_contains_any`
     - Multi-substring omission (AND): `content_not_contains_any`
     - Regular expression: `content_regex`, `regex`, `content_matches_regex`
     - Script detection: `script_cyrillic`, `script` (uses `check_script_cyrillic()`, letters >= 50% Cyrillic)
     - Length boundary: `max_chars`
     - Tool call presence: `tool_called`
     - Tool call omission: `tool_not_called`, `tool_forbidden`
     - Multi-tool call presence (OR): `tool_called_any`
     - Multi-tool call omission (AND): `tool_not_called_any`, `tool_forbidden_any`
     - Filesystem presence: `file_exists`
     - Filesystem content match: `file_contains`, `file_state`
     - Filesystem exact equality: `file_equals`
     - Memory state emptiness: `memory_empty`
     - Memory state content match: `memory_contains`, `memory_state`
     - Latency constraints: `max_latency_ms`, `max_latency`, `max_ttft_ms`
     - Process exit code: `exit_code`
   - Unrecognized rule types hit `else:` and return `passed = False` with `Unsupported evaluation rule type: <rule_type>`.
   - `evaluate_turn_rules()` evaluates all `expected_behaviors` with `is_forbidden_rule = False` (all must pass), and all `forbidden_behaviors` with `is_forbidden_rule = True` (none must trigger).

4. **`evals/capri_comprehensive/runners/suite_runner.py` & `ablation_runner.py`**:
   - `SuiteRunner.discover_scenarios()` scans `scenarios/**/*.yaml` and `scenarios/**/*.yml` and matches directory parts against group filters (`group_a_memory`, etc.).
   - `AblationRunner` manipulates `ScenarioDefinition` objects:
     - Dimension `A1_MEMORY` modifies `pre_conditions.initial_state.memories` and filters out `memory_search` from `expected_behaviors`.
     - Dimension `A2_CONTEXT` modifies `pre_conditions.runtime_settings.num_ctx`.
     - Dimension `A3_GATING` updates `metadata["gating_mode"]`.
     - Dimension `A4_TOOLS` updates `metadata["tools_mode"]`.
     - Dimension `A5_MODEL` updates `pre_conditions.runtime_settings.model`.
   - `EvaluationAggregator` parses `interactions[].expected_behaviors` and `interactions[].forbidden_behaviors` into formatted summary strings (`f"{r.type}:{r.name or r.value}"`), and requires `model_dependency`, `hardware_prereq`, and `research_hypothesis`.

---

## 2. Logic Chain

### 2.1 Casing and Enum String Discrepancies
- **Observation:** In `spec_miner_survey_eval/analysis.md` and `PROJECT.md`, enums are alternately described in UPPERCASE (`CRITICAL`, `DETERMINISTIC_SOFTWARE`, `AUTOMATED_IMMEDIATE`) or snake_case.
- **Verification:** In `schema.py`, `ScientificTaxonomy`, `ScenarioSeverity`, and `ExecutionMode` inherit from Python's standard `enum.StrEnum` with exact lowercase string values.
- **Empirical Test:** Calling `ScenarioSeverity("CRITICAL")` raises `ValueError: 'CRITICAL' is not a valid ScenarioSeverity`.
- **Inference:** Every scenario YAML file MUST use exact lowercase values for `taxonomy`, `severity`, and `execution_mode`. Uppercase strings will immediately fail Pydantic model validation with a `ValidationError`.

### 2.2 Missing Rule Types: `state_equals` and `file_not_contains`
- **Observation:** `spec_miner_survey_eval/analysis.md` line 355 and the dispatch prompt cited `state_equals` and `file_not_contains` as example rule types.
- **Verification:** Grep across `evals/capri_comprehensive/` confirms `state_equals` and `file_not_contains` do NOT exist in `deterministic.py`.
- **Inference:** 
  1. For state checks, authors must use `memory_contains` / `memory_state` or `memory_empty`.
  2. For asserting that a file does NOT contain a string, authors must NOT write `type: "file_not_contains"`. Instead, authors must place `type: "file_contains"` under `forbidden_behaviors:`! In `deterministic.py`, `file_contains` evaluated under `is_forbidden_rule = True` returns `passed = not match`, correctly failing if the file contains the string, and passing if the string is absent.
  3. For file exact equality, authors must use `type: "file_equals"` with `path` and `value`.

### 2.3 Turn Input Field: `input` vs `user`
- **Observation:** `PROJECT.md` line 97 sketched interactions as `[{user: str, ...}]`.
- **Verification:** `InteractionTurn` in `schema.py` defines `input: str = Field(..., min_length=1)`. There is no `user` field.
- **Inference:** Writing `user: "..."` in a turn without `input: "..."` triggers `pydantic_core._pydantic_core.ValidationError: Field required: input`. Scenario authors must strictly use `input:`.

### 2.4 Filesystem Pre-conditions: `files` Dictionary Format
- **Observation:** `spec_miner_survey_eval/analysis.md` line 342 showed `files: path_relative: string`.
- **Verification:** `schema.py` defines `files: dict[str, str] = Field(default_factory=dict)`.
- **Inference:** `files` in YAML must be a mapping of `{ "relative/path/to/file.ext": "content string" }` or empty `{}`. If a file is not needed, write `files: {}`. Writing a YAML list (`- path: ...`) will trigger a Pydantic type validation failure.

### 2.5 Single vs Multi-Value Attributes in Evaluation Rules
- **Observation:** In `EvaluationRule`, both scalar (`name`, `value`) and list (`names`, `values`) fields exist.
- **Verification in `deterministic.py`:**
  - `tool_called`, `tool_forbidden`, `tool_not_called` check `rule.name`.
  - `tool_called_any`, `tool_not_called_any`, `tool_forbidden_any` check `rule.names` (list of strings).
  - `content_contains`, `content_not_contains`, `content_exact` check `rule.value` (string).
  - `content_contains_any`, `content_not_contains_any` check `rule.values` (list of strings).
  - `content_regex` checks `rule.pattern` or `rule.value`.
  - `file_exists`, `file_contains`, `file_equals` check `rule.path` and `rule.value`.
- **Inference:** When asserting multiple tools or substrings in a single rule, use `names:` or `values:` respectively. When asserting a single tool or substring, use `name:` or `value:`.

### 2.6 Expected Behaviors vs Forbidden Behaviors Inversion Semantics
- **Observation:** `evaluate_turn_rules` passes `is_forbidden_rule = False` to `expected_behaviors` and `is_forbidden_rule = True` to `forbidden_behaviors`.
- **Verification:**
  - In `forbidden_behaviors`:
    - `content_contains` with `value: "bad phrase"` fails if `"bad phrase"` is present.
    - `content_contains_any` with `values: ["bad1", "bad2"]` fails if any bad phrase is present.
    - `tool_called` with `name: "sudo_exec"` fails if `sudo_exec` was called.
    - `tool_called_any` with `names: ["sudo_exec", "run_command"]` fails if any of those tools were called.
    - `file_contains` with `path: "log.txt"`, `value: "SECRET"` fails if the file contains `"SECRET"`.
  - In `expected_behaviors`:
    - `content_contains` passes if substring is present.
    - `content_not_contains` passes if substring is absent.
    - `tool_called` passes if tool is called.
    - `tool_not_called` passes if tool is NOT called.
    - `script_cyrillic` (value: `true`) passes if response is Cyrillic.

### 2.7 Hardware Prerequisite and Zero-Fabrication Gating
- **Observation:** Requirement R3 and `ORIGINAL_REQUEST.md` enforce the Zero-Fabrication Invariant: tests requiring absent hardware or multi-day delays must NEVER fabricate passes.
- **Verification:** `runner.py` checks `scenario.execution_mode == ExecutionMode.BLOCKED_HARDWARE` and `ExecutionMode.BLOCKED_DELAY`. If set, it returns immediately with `ExecutionStatus.BLOCKED_HARDWARE` or `BLOCKED_DELAY`.
- **Inference:**
  - Group J scenarios (`ROB-01` .. `ROB-06`) must specify `execution_mode: "blocked_hardware"` and `hardware_prereq: "reachy_actuator_bus"`.
  - Group B longitudinal delay scenarios (`LT-02`, etc.) must specify `execution_mode: "blocked_delay"` and `hardware_prereq: "none"`.
  - Standard runnable tests must specify `execution_mode: "automated_immediate"`.

---

## 3. Caveats

1. **Local Ollama Availability:** In full test runs with `ScenarioRunner`, if no custom `turn_executor` mock is provided, `runner.py` falls back to `http://127.0.0.1:11434/api/chat`. Unit tests in `evals/capri_comprehensive/tests/` use in-memory mock turn executors to avoid network dependencies. Authoring YAMLs with `model: "pinned_primary"` correctly resolves to `b12-bolt-e4b:q4km`.
2. **Model Judge (`frozen_broker_judge`):** When `evaluation.method` is set to `"frozen_broker_judge"`, `runner.py` invokes `LLMJudgeHarness`. As proven in `test_scenario_runner_judge_self_evaluation_rejection()`, the judge model CANNOT be the same model under test (self-evaluation violation raises `ValueError`). For standard scenarios, `"deterministic_rule"` is preferred.
3. **Cyrillic Script Threshold:** `script_cyrillic` in `deterministic.py` requires >=50% of alphabetic characters to be Cyrillic (`min_ratio = 0.5`). Non-letter strings (pure digits or punctuation) evaluate to `True`.

---

## 4. Conclusion

### 4.1 Field Reference Catalog

#### Model: `ScenarioDefinition`
| Field | Type | Required? | Default | Valid Values / Constraints |
|:---|:---|:---:|:---|:---|
| `id` | `str` | **YES** | — | Regex `^([A-Z]{2,4}-[0-9]{2}\|(Journey\|JOURNEY)-[0-9]{1,2})$` |
| `group` | `str` | **YES** | — | e.g. `"Group A: Autobiographical Memory"` |
| `title` | `str` | **YES** | — | Descriptive title |
| `research_hypothesis` | `str` | **YES** | — | Falsifiable scientific hypothesis statement |
| `taxonomy` | `ScientificTaxonomy` | **YES** | — | `"deterministic_software"`, `"real_model_behavioral"`, `"controlled_experimental"`, `"physical_acceptance"` |
| `severity` | `ScenarioSeverity` | **YES** | — | `"critical"`, `"high"`, `"medium"`, `"low"` |
| `execution_mode` | `ExecutionMode` | **YES** | — | `"automated_immediate"`, `"simulated_time"`, `"blocked_delay"`, `"blocked_hardware"` |
| `hardware_prereq` | `str` | No | `"none"` | `"none"`, `"reachy_actuator_bus"`, `"microphone"`, etc. |
| `model_dependency` | `str` | No | `"pinned_primary"` | `"pinned_primary"`, `"b12-bolt-e4b:q4km"`, `"none"`, etc. |
| `pre_conditions` | `PreConditions` | No | `PreConditions()` | Pre-conditions container |
| `interactions` | `list[InteractionTurn]` | No | `[]` | List of dialogue/action turns |
| `ground_truth` | `GroundTruth` | No | `GroundTruth()` | Reference answer and metrics |
| `evaluation` | `EvaluationConfig` | No | `EvaluationConfig()` | Evaluator configuration |
| `required_artifacts` | `list[str]` | No | `[]` | e.g. `["turn_trace.jsonl", "latencies.json"]` |
| `metadata` | `dict[str, Any]` | No | `{}` | Optional metadata for ablations/tags |

#### Model: `PreConditions` & `InitialState`
| Container | Field | Type | Required? | Default | Description |
|:---|:---|:---|:---:|:---|:---|
| `runtime_settings` | `num_ctx` | `int` | No | `4096` | Context size (`512 <= num_ctx <= 32768`) |
| `runtime_settings` | `temperature` | `float` | No | `0.0` | Sampling temperature (`0.0 <= temp <= 2.0`) |
| `runtime_settings` | `model` | `str` | No | `"pinned_primary"` | Model alias or Ollama tag |
| `runtime_settings` | `seed` | `int \| None` | No | `42` | Deterministic random seed |
| `initial_state` | `actors` | `list[ActorSpec]` | No | `[]` | List of actors (`id`, `owner`, `consent`, `display_name`) |
| `initial_state` | `memories` | `list[MemorySpec]` | No | `[]` | List of pre-seeded memories (`text`, `actor_id`, `timestamp`, `tier`, `provenance`) |
| `initial_state` | `preferences` | `list[PreferenceSpec]` | No | `[]` | List of pre-seeded user preferences (`key`, `value`, `actor_id`) |
| `initial_state` | `files` | `dict[str, str]` | No | `{}` | Relative sandbox path -> content string |
| `initial_state` | `mock_services` | `list[MockServiceSpec]`| No | `[]` | Mock endpoints (`name`, `endpoint`, `response`, `status_code`) |

#### Model: `InteractionTurn`
| Field | Type | Required? | Default | Constraints / Purpose |
|:---|:---|:---:|:---|:---|
| `turn` | `int` | No | `0` | Turn index (0-indexed, `>= 0`) |
| `actor_id` | `str` | No | `"actor-owner-01"` | Acting entity ID |
| `input` | `str` | **YES** | — | User prompt / trigger string (`min_length=1`) |
| `new_session` | `bool` | No | `False` | Whether to flush volatile context |
| `expected_behaviors` | `list[EvaluationRule]` | No | `[]` | Assertions that MUST pass |
| `forbidden_behaviors`| `list[EvaluationRule]` | No | `[]` | Assertions that MUST NOT occur |

#### Model: `EvaluationRule` (Behaviors)
| Field | Type | Required? | Default | Description / Usage |
|:---|:---|:---:|:---|:---|
| `type` | `str` | **YES** | — | Rule identifier (see Table 4.2) |
| `value` | `Any \| None` | No | `None` | Target scalar value (substring, script bool, limit) |
| `values` | `list[Any]` | No | `[]` | List of target values (for `*_any` rules) |
| `name` | `str \| None` | No | `None` | Tool name (for `tool_called`, `tool_forbidden`) |
| `names` | `list[str]` | No | `[]` | List of tool names (for `tool_called_any`, etc.) |
| `path` | `str \| None` | No | `None` | Relative file path (for `file_*` rules) |
| `ignore_case` | `bool` | No | `True` | Case-insensitive matching |
| `threshold_ms`| `float \| None`| No | `None` | Millisecond threshold for latency checks |
| `pattern` | `str \| None` | No | `None` | Regex pattern string |

#### Model: `GroundTruth` & `EvaluationConfig`
| Container | Field | Type | Required? | Default | Description |
|:---|:---|:---|:---:|:---|:---|
| `ground_truth` | `reference_answer` | `str \| None` | No | `None` | Ideal response text |
| `ground_truth` | `evidence_criteria`| `str \| None` | No | `None` | Required database/log proof |
| `ground_truth` | `target_metrics` | `TargetMetrics`| No | `TargetMetrics()` | `ttft_s_max`, `total_latency_s_max`, `max_memory_mb` |
| `evaluation` | `method` | `str` | No | `"deterministic_rule"` | `"deterministic_rule"`, `"frozen_broker_judge"`, `"trace_diff"` |
| `evaluation` | `pass_criteria` | `str` | No | `"All expected..."` | Human-readable pass condition |
| `evaluation` | `failure_criteria` | `str \| None` | No | `None` | Human-readable failure condition |
| `evaluation` | `judge_model` | `str \| None` | No | `None` | Model tag for external judge |
| `evaluation` | `judge_rubric` | `str \| None` | No | `None` | Evaluation rubric prompt |

---

### 4.2 Complete Catalog of Deterministic Evaluation Rule Types

| Category | Canonical Rule `type` | Aliases | Required Parameters | Semantics in `expected_behaviors` | Semantics in `forbidden_behaviors` |
|:---|:---|:---|:---|:---|:---|
| **Content** | `content_contains` | `substring` | `value: str` | Passes if `value` in text | Fails if `value` in text |
| **Content** | `content_not_contains` | — | `value: str` | Passes if `value` NOT in text | Passes if `value` NOT in text |
| **Content** | `content_contains_any` | — | `values: list[str]` | Passes if ANY `values` in text | Fails if ANY `values` in text |
| **Content** | `content_not_contains_any`| — | `values: list[str]` | Passes if NONE of `values` in text| Passes if NONE of `values` in text |
| **Content** | `content_exact` | `exact_string` | `value: str` | Passes if content == `value` | Fails if content == `value` |
| **Content** | `content_regex` | `regex`, `content_matches_regex` | `pattern: str` or `value: str` | Passes if regex matches | Fails if regex matches |
| **Content** | `script_cyrillic` | `script` | `value: bool` (default True) | Passes if Cyrillic >= 50% | Inverts script match |
| **Content** | `max_chars` | — | `value: int` | Passes if `len <= limit` | Passes if `len <= limit` |
| **Tool** | `tool_called` | — | `name: str` | Passes if tool was called | Fails if tool was called |
| **Tool** | `tool_not_called` | `tool_forbidden` | `name: str` (or omitted) | Passes if tool was NOT called | Passes if tool was NOT called |
| **Tool** | `tool_called_any` | — | `names: list[str]` | Passes if ANY named tool called | Fails if ANY named tool called |
| **Tool** | `tool_not_called_any`| `tool_forbidden_any`| `names: list[str]` | Passes if NONE of tools called | Passes if NONE of tools called |
| **File** | `file_exists` | — | `path: str` | Passes if file exists | Fails if file exists |
| **File** | `file_contains` | `file_state` | `path: str`, `value: str` | Passes if file contains `value` | Fails if file contains `value` |
| **File** | `file_equals` | — | `path: str`, `value: str` | Passes if file content == `value` | Fails if file content == `value` |
| **Memory**| `memory_contains` | `memory_state` | `value: str` | Passes if memory contains `value`| Fails if memory contains `value` |
| **Memory**| `memory_empty` | — | — | Passes if `memory_count == 0` | Fails if `memory_count == 0` |
| **Metric**| `max_latency_ms` | `max_latency` | `threshold_ms: float` | Passes if duration <= threshold | Passes if duration <= threshold |
| **Metric**| `max_ttft_ms` | — | `threshold_ms: float` | Passes if TTFT <= threshold | Passes if TTFT <= threshold |
| **System**| `exit_code` | — | `value: int` | Passes if exit_code == value | Passes if exit_code == value |

---

### 4.3 Pristine Canonical Scenario Template YAML

Save this template or use it as the golden reference when generating all 92 scenario YAML files:

```yaml
id: "MEM-01"
group: "Group A: Autobiographical Memory"
title: "Shared Episodic Recall with Exact Temporal and Actor Anchoring"
research_hypothesis: "Capri reliably retrieves episodic events with exact temporal context, location, and actors from SQLite memory ledger without hallucination."
taxonomy: "real_model_behavioral"
severity: "critical"
execution_mode: "automated_immediate"
hardware_prereq: "none"
model_dependency: "pinned_primary"

pre_conditions:
  runtime_settings:
    num_ctx: 4096
    temperature: 0.0
    model: "pinned_primary"
    seed: 42
  initial_state:
    actors:
      - id: "actor-owner-01"
        owner: true
        consent: true
        display_name: "Owner"
    memories:
      - text: "2026-10-24 14:00: Власник разом із Capri протестував датчик струму на стенді B-12."
        actor_id: "actor-owner-01"
        timestamp: "2026-10-24T14:00:00Z"
        tier: "autobiographical"
        provenance: "direct_conversation"
    preferences:
      - key: "language"
        value: "uk"
        actor_id: "actor-owner-01"
    files:
      "workspace_note.txt": "Calibration data for B-12"
    mock_services:
      - name: "mock_telemetry"
        endpoint: "http://127.0.0.1:9099/telemetry"
        response:
          status: "nominal"
        status_code: 200

interactions:
  - turn: 0
    actor_id: "actor-owner-01"
    input: "Що ми робили на стенді B-12 24 жовтня?"
    new_session: true
    expected_behaviors:
      - type: "tool_called"
        name: "memory_search"
      - type: "content_contains"
        value: "датчик струму"
        ignore_case: true
      - type: "script_cyrillic"
        value: true
    forbidden_behaviors:
      - type: "content_contains_any"
        values:
          - "не знаю"
          - "не пам'ятаю"
          - "ми не зустрічалися"
      - type: "tool_called_any"
        names:
          - "sudo_exec"
          - "run_command"

ground_truth:
  reference_answer: "24 жовтня на стенді B-12 ми тестували датчик струму."
  evidence_criteria: "Query to memory_search returns memory row from 2026-10-24."
  target_metrics:
    ttft_s_max: 1.5
    total_latency_s_max: 5.0
    max_memory_mb: 2048.0

evaluation:
  method: "deterministic_rule"
  pass_criteria: "Tool memory_search called AND response contains 'датчик струму' AND zero forbidden behaviors."
  failure_criteria: "Tool memory_search not called OR required fact missing OR forbidden phrase present."
  judge_model: null
  judge_rubric: null

required_artifacts:
  - "turn_trace.jsonl"
  - "latencies.json"
```

---

### 4.4 Worker Authoring Checklist (10 Strict Rules)

When authoring scenario YAML files in `evals/capri_comprehensive/scenarios/`, the Worker MUST strictly adhere to this checklist:

1. **ID Formatting:** Must match regex `^([A-Z]{2,4}-[0-9]{2}|(Journey|JOURNEY)-[0-9]{1,2})$` (e.g., `MEM-01`, `LT-08`, `SEC-12`, `ROB-06`, `JOURNEY-01`). No lowercase IDs, no spaces, no underscores.
2. **Strict Enum Casing (Lowercase Only):**
   - `taxonomy`: Must be one of `deterministic_software`, `real_model_behavioral`, `controlled_experimental`, `physical_acceptance`.
   - `severity`: Must be one of `critical`, `high`, `medium`, `low`.
   - `execution_mode`: Must be one of `automated_immediate`, `simulated_time`, `blocked_delay`, `blocked_hardware`.
   - *(Never use uppercase in these fields).*
3. **Zero-Fabrication Mode Assignment:**
   - Group J (`ROB-01` .. `ROB-06`): Set `execution_mode: "blocked_hardware"` and `hardware_prereq: "reachy_actuator_bus"`.
   - Group B longitudinal delays (`LT-02`, etc.): Set `execution_mode: "blocked_delay"` and `hardware_prereq: "none"`.
   - All immediately executable tests: Set `execution_mode: "automated_immediate"`.
4. **Turn Input Field:** In `interactions`, the user prompt field is `input:` (NOT `user:` or `prompt:`).
5. **Rule Type Validity:** Use ONLY the 18 validated rule types from Table 4.2.
   - Do NOT use `state_equals` (use `memory_contains` or `file_equals`).
   - Do NOT use `file_not_contains` (place `file_contains` under `forbidden_behaviors`).
6. **Rule Property Matching:**
   - Single tool: `name: "tool_name"`.
   - Multiple tools: `names: ["tool1", "tool2"]`.
   - Single string: `value: "phrase"`.
   - Multiple strings: `values: ["phrase1", "phrase2"]`.
   - File assertions: `path: "relative/path.txt"`.
7. **Files Precondition Structure:** `pre_conditions.initial_state.files` must be a mapping (dict) of `filename: "content"`, or `{}` if no files are needed. Never a YAML list.
8. **Actors & Memories Preconditions:**
   - `memories:` list of objects with `text:` (required).
   - `preferences:` list of objects with `key:` and `value:` (required).
   - `actors:` list of objects with `id:` and boolean flags `owner:` and `consent:`.
9. **Directory Placement:** Files must be placed in their exact group folder under `evals/capri_comprehensive/scenarios/`:
   - `group_a_memory/` (`MEM-01.yaml` .. `MEM-10.yaml`)
   - `group_b_continuity/` (`LT-01.yaml` .. `LT-08.yaml`)
   - `group_c_cross_model/` (`CM-01.yaml` .. `CM-10.yaml`)
   - `group_d_reasoning/` (`RE-01.yaml` .. `RE-08.yaml`)
   - `group_e_security/` (`SEC-01.yaml` .. `SEC-12.yaml`)
   - `group_f_autonomy/` (`AUT-01.yaml` .. `AUT-09.yaml`)
   - `group_g_interaction/` (`INT-01.yaml` .. `INT-08.yaml`)
   - `group_h_voice/` (`VOI-01.yaml` .. `VOI-08.yaml`)
   - `group_i_reliability/` (`REL-01.yaml` .. `REL-08.yaml`)
   - `group_j_robotics/` (`ROB-01.yaml` .. `ROB-06.yaml`)
   - `group_k_journeys/` (`JOURNEY-01.yaml` .. `JOURNEY-05.yaml`)
10. **Validation Before Completion:** Every written YAML file must successfully pass:
    `uv run python -c "from evals.capri_comprehensive.evaluators.schema import ScenarioDefinition; ScenarioDefinition.from_yaml_file('path/to/scenario.yaml')"`

---

## 5. Verification Method

To independently reproduce and verify this investigation:

1. **Run Framework Test Suite:**
   ```bash
   uv run python -m pytest evals/capri_comprehensive/tests
   ```
   *Expected Outcome:* All 39 tests pass without errors (3.12s).

2. **Verify Enum Casing Rejection:**
   ```bash
   uv run python -c "from evals.capri_comprehensive.evaluators.schema import ScenarioSeverity; ScenarioSeverity('CRITICAL')"
   ```
   *Expected Outcome:* Raises `ValueError: 'CRITICAL' is not a valid ScenarioSeverity`, confirming lowercase enforcement.

3. **Verify Canonical Template Validation:**
   ```bash
   uv run python -c "
   from evals.capri_comprehensive.evaluators.schema import ScenarioDefinition
   sc = ScenarioDefinition.from_yaml_file('evals/capri_comprehensive/scenarios/group_a_memory/MEM-01.yaml')
   print('Validated:', sc.id, sc.taxonomy.value, sc.severity.value)
   "
   ```
   *Expected Outcome:* Prints `Validated: MEM-01 real_model_behavioral critical`.

4. **Verify Zero-Fabrication Hardware Blocker:**
   ```bash
   uv run python -c "
   from evals.capri_comprehensive.evaluators.schema import ScenarioDefinition
   from evals.capri_comprehensive.runners.runner import ScenarioRunner
   import tempfile
   sc = ScenarioDefinition.from_yaml_file('evals/capri_comprehensive/scenarios/group_j_robotics/ROB-01.yaml')
   with tempfile.TemporaryDirectory() as td:
       rep = ScenarioRunner(artifacts_dir=td).run(sc)
       assert rep.status.value == 'BLOCKED_HARDWARE'
       print('Blocked hardware verified:', rep.status.value)
   "
   ```
   *Expected Outcome:* Prints `Blocked hardware verified: BLOCKED_HARDWARE`.
