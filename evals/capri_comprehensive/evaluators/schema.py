"""Pydantic V2 schema models for Capri Comprehensive Evaluation.

Provides strict data validation for:
- Scenario definitions (YAML)
- Pre-conditions, actors, memories, files, mocks
- Multi-turn interaction sequences and rule assertions
- Execution outcomes and structured report models
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class ScientificTaxonomy(StrEnum):
    """Four-tier scientific taxonomy mandated by methodology."""

    DETERMINISTIC_SOFTWARE = "deterministic_software"
    REAL_MODEL_BEHAVIORAL = "real_model_behavioral"
    CONTROLLED_EXPERIMENTAL = "controlled_experimental"
    PHYSICAL_ACCEPTANCE = "physical_acceptance"


class ScenarioSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ExecutionMode(StrEnum):
    AUTOMATED_IMMEDIATE = "automated_immediate"
    SIMULATED_TIME = "simulated_time"
    BLOCKED_DELAY = "blocked_delay"
    BLOCKED_HARDWARE = "blocked_hardware"


class ExecutionStatus(StrEnum):
    EXECUTED_PASS = "EXECUTED_PASS"
    EXECUTED_FAIL = "EXECUTED_FAIL"
    BLOCKED_HARDWARE = "BLOCKED_HARDWARE"
    BLOCKED_DELAY = "BLOCKED_DELAY"
    PENDING = "PENDING"
    SKIPPED = "SKIPPED"


class RuntimeSettings(BaseModel):
    num_ctx: int = Field(default=4096, ge=512, le=32768)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    model: str = Field(default="pinned_primary")
    seed: int | None = 42


class ActorSpec(BaseModel):
    id: str = Field(default="actor-owner-01")
    owner: bool = True
    consent: bool = True
    display_name: str | None = None


class MemorySpec(BaseModel):
    text: str
    actor_id: str = "actor-owner-01"
    timestamp: str = "2026-10-24T14:00:00Z"
    tier: str | None = "autobiographical"
    provenance: str | None = "direct_conversation"


class PreferenceSpec(BaseModel):
    key: str
    value: str
    actor_id: str = "actor-owner-01"


class MockServiceSpec(BaseModel):
    name: str
    endpoint: str
    response: Any = None
    status_code: int = 200


class InitialState(BaseModel):
    actors: list[ActorSpec] = Field(default_factory=list)
    memories: list[MemorySpec] = Field(default_factory=list)
    preferences: list[PreferenceSpec] = Field(default_factory=list)
    files: dict[str, str] = Field(default_factory=dict)
    mock_services: list[MockServiceSpec] = Field(default_factory=list)


class PreConditions(BaseModel):
    runtime_settings: RuntimeSettings = Field(default_factory=RuntimeSettings)
    initial_state: InitialState = Field(default_factory=InitialState)


class EvaluationRule(BaseModel):
    """Specification of an expected or forbidden assertion on interaction turns or state."""

    type: str  # content_contains, content_not_contains, tool_called, tool_forbidden, etc.
    value: Any | None = None
    values: list[Any] = Field(default_factory=list)
    name: str | None = None
    names: list[str] = Field(default_factory=list)
    path: str | None = None
    ignore_case: bool = True
    turn: int | None = None
    threshold_ms: float | None = None
    pattern: str | None = None


class InteractionTurn(BaseModel):
    turn: int = Field(default=0, ge=0)
    actor_id: str = Field(default="actor-owner-01")
    input: str = Field(..., min_length=1)
    new_session: bool = False
    expected_behaviors: list[EvaluationRule] = Field(default_factory=list)
    forbidden_behaviors: list[EvaluationRule] = Field(default_factory=list)


class TargetMetrics(BaseModel):
    ttft_s_max: float | None = None
    total_latency_s_max: float | None = None
    max_memory_mb: float | None = None


class GroundTruth(BaseModel):
    reference_answer: str | None = None
    evidence_criteria: str | None = None
    target_metrics: TargetMetrics = Field(default_factory=TargetMetrics)


class EvaluationConfig(BaseModel):
    method: str = Field(
        default="deterministic_rule"
    )  # deterministic_rule | frozen_broker_judge | trace_diff
    pass_criteria: str = Field(
        default="All expected behaviors satisfied and zero forbidden behaviors."
    )
    failure_criteria: str | None = None
    judge_model: str | None = None
    judge_rubric: str | None = None


class ScenarioDefinition(BaseModel):
    """Authoritative schema for all Capri evaluation scenarios across Groups A-K."""

    id: str = Field(..., pattern=r"^([A-Z]{2,4}-[0-9]{2}|(Journey|JOURNEY)-[0-9]{1,2})$")
    group: str
    title: str
    research_hypothesis: str
    taxonomy: ScientificTaxonomy
    severity: ScenarioSeverity
    execution_mode: ExecutionMode
    hardware_prereq: str = Field(default="none")
    model_dependency: str = Field(default="pinned_primary")

    pre_conditions: PreConditions = Field(default_factory=PreConditions)
    interactions: list[InteractionTurn] = Field(default_factory=list)
    ground_truth: GroundTruth = Field(default_factory=GroundTruth)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    required_artifacts: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_yaml_file(cls, path: str | Path) -> ScenarioDefinition:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Scenario YAML file not found: {p}")
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    @classmethod
    def from_yaml_str(cls, content: str) -> ScenarioDefinition:
        data = yaml.safe_load(content)
        return cls.model_validate(data)

    def to_yaml_str(self) -> str:
        return yaml.dump(self.model_dump(mode="json"), sort_keys=False, allow_unicode=True)


class AssertionOutcome(BaseModel):
    rule_type: str
    passed: bool
    detail: str
    expected: Any | None = None
    actual: Any | None = None
    turn: int | None = None


class TurnExecutionResult(BaseModel):
    turn_index: int
    prompt: str
    response_content: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    ttft_ms: float = 0.0
    total_duration_ms: float = 0.0
    passed: bool = True
    passed_assertions: list[AssertionOutcome] = Field(default_factory=list)
    failed_assertions: list[AssertionOutcome] = Field(default_factory=list)
    tokens_prompt: int = 0
    tokens_completion: int = 0
    state_snapshot: dict[str, Any] = Field(default_factory=dict)


class ExecutionReport(BaseModel):
    """Standardized report produced by scenario execution."""

    scenario_id: str
    group: str
    title: str
    taxonomy: ScientificTaxonomy
    severity: ScenarioSeverity
    execution_mode: ExecutionMode
    status: ExecutionStatus
    blocker_reason: str | None = None
    turn_results: list[TurnExecutionResult] = Field(default_factory=list)
    all_passed: bool = False
    latencies_ms: list[float] = Field(default_factory=list)
    ttft_ms_list: list[float] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    started_at: str
    completed_at: str
    tokens_prompt: int = 0
    tokens_completion: int = 0
    judge_evaluations: list[dict[str, Any]] = Field(default_factory=list)
    ablation_condition: str | None = None
    raw_score: float = 0.0  # 1.0 for pass, 0.0 for fail
