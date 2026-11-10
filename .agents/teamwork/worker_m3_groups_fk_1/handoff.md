# Handoff Report: Scenario Authoring Groups F–K & Fixtures (Milestone M3)

**Author:** Worker 2 (`worker_m3_groups_fk_1`)  
**Date:** 2026-11-10  
**Milestone:** M3 (Scenario Definitions & Fixtures)  
**Deliverable Path:** `/home/cyberdid/Projects/B-12/.agents/teamwork/worker_m3_groups_fk_1/handoff.md`

---

## 1. Observation

This deliverable implemented and validated all 44 assigned evaluation scenario YAML files across Groups F through K and created supporting synthetic test fixtures in `evals/capri_comprehensive/fixtures/`.

### 1.1 Direct Source Observations & Created Files

1. **Group F: Autonomy & Initiative (`evals/capri_comprehensive/scenarios/group_f_autonomy/`)**:
   - `AUT-01.yaml`: Autonomous Goal Decomposition and Execution within Turn Budget (`real_model_behavioral`, `high`, `automated_immediate`).
   - `AUT-02.yaml`: Proactive Notification Utility Filtering and Relevance (`controlled_experimental`, `high`, `automated_immediate`).
   - `AUT-03.yaml`: Strict Suppression of Proactivity During Quiet Hours (`deterministic_software`, `critical`, `automated_immediate`).
   - `AUT-04.yaml`: Exponential Backoff on Unacknowledged Proactive Prompts (`deterministic_software`, `high`, `automated_immediate`).
   - `AUT-05.yaml`: Immediate Task Cancellation on Owner Emergency Stop (`deterministic_software`, `critical`, `automated_immediate`).
   - `AUT-06.yaml`: Autonomous Background Memory Consolidation and Reflection (`real_model_behavioral`, `medium`, `automated_immediate`).
   - `AUT-07.yaml`: Curiosity-Driven Exploration of Past Unresolved Failures (`real_model_behavioral`, `medium`, `automated_immediate`).
   - `AUT-08.yaml`: Checkpoint-Based Long-Running Task Resumption Post-Crash (`deterministic_software`, `high`, `automated_immediate`).
   - `AUT-09.yaml`: Priority-Based Task Preemption and Scheduler Fairness (`deterministic_software`, `high`, `automated_immediate`).

2. **Group G: Human–AI Interaction (`evals/capri_comprehensive/scenarios/group_g_interaction/`)**:
   - `INT-01.yaml`: Empathetic Tone Attunement Without Sycophancy (`real_model_behavioral`, `medium`, `automated_immediate`).
   - `INT-02.yaml`: Constructive Technical Dissent Against Hazardous User Assumptions (`real_model_behavioral`, `critical`, `automated_immediate`).
   - `INT-03.yaml`: Spoken Conciseness and Natural Conversational Turn-Taking (`real_model_behavioral`, `high`, `automated_immediate`).
   - `INT-04.yaml`: Intent Disambiguation and Clarifying Question Calibration (`real_model_behavioral`, `high`, `automated_immediate`).
   - `INT-05.yaml`: Cybercat Construct Persona and Contextual Wit (`real_model_behavioral`, `low`, `automated_immediate`).
   - `INT-06.yaml`: Strict Adherence to Personal and Domain Boundaries (`real_model_behavioral`, `high`, `automated_immediate`).
   - `INT-07.yaml`: Actor Differentiation and Owner Primacy in Multi-Party Dialogue (`real_model_behavioral`, `high`, `automated_immediate`).
   - `INT-08.yaml`: Natural Grounding in Shared Episodic Experiences (`real_model_behavioral`, `low`, `automated_immediate`).

3. **Group H: Voice & Real-Time Interaction (`evals/capri_comprehensive/scenarios/group_h_voice/`)**:
   - `VOI-01.yaml`: Time-To-First-Token on Cold Model Loading (`controlled_experimental`, `high`, `automated_immediate`).
   - `VOI-02.yaml`: Warm Conversational Turn-Taking Latency Budget (`controlled_experimental`, `critical`, `automated_immediate`).
   - `VOI-03.yaml`: Text Sanitization and Phonetic Readiness for Speech Synthesis (`real_model_behavioral`, `high`, `automated_immediate`).
   - `VOI-04.yaml`: Sub-300ms Audio Playback Cancellation on User Barge-In (`physical_acceptance`, `critical`, `blocked_hardware`, `hardware_prereq: "audio_mic_speaker_rig"`).
   - `VOI-05.yaml`: Continuous Audio Playback During Background Tool Execution (`physical_acceptance`, `critical`, `blocked_hardware`, `hardware_prereq: "audio_mic_speaker_rig"`).
   - `VOI-06.yaml`: Acoustic Echo Cancellation and TTS Self-Feedback Immunity (`physical_acceptance`, `critical`, `blocked_hardware`, `hardware_prereq: "audio_mic_speaker_rig"`).
   - `VOI-07.yaml`: Voice Activity Detection End-of-Speech Boundary Precision (`physical_acceptance`, `high`, `blocked_hardware`, `hardware_prereq: "audio_mic_speaker_rig"`).
   - `VOI-08.yaml`: Subtle Backchannel Vocalizations During Extended User Turns (`physical_acceptance`, `medium`, `blocked_hardware`, `hardware_prereq: "audio_mic_speaker_rig"`).

4. **Group I: Reliability & Fault Tolerance (`evals/capri_comprehensive/scenarios/group_i_reliability/`)**:
   - `REL-01.yaml`: SQLite Busy Locking and Crash-Safe Transaction Recovery (`deterministic_software`, `critical`, `automated_immediate`).
   - `REL-02.yaml`: Graceful Handling of Model Daemon Socket Disconnection (`deterministic_software`, `critical`, `automated_immediate`).
   - `REL-03.yaml`: Hard Tool Execution Timeout and Orphan Process Termination (`deterministic_software`, `high`, `automated_immediate`).
   - `REL-04.yaml`: Graceful Context Truncation on Oversized Inputs (`controlled_experimental`, `high`, `automated_immediate`).
   - `REL-05.yaml`: Safe Serialization of Concurrent State Mutations (`deterministic_software`, `high`, `automated_immediate`).
   - `REL-06.yaml`: Safe Write Rejection Under Low Disk Storage Threshold (`deterministic_software`, `high`, `automated_immediate`).
   - `REL-07.yaml`: Clean Signal Trapping, WAL Flushing, and Lock File Cleanup (`deterministic_software`, `high`, `automated_immediate`).
   - `REL-08.yaml`: Bit-for-Bit Deterministic State Reconstruction from Event Ledger (`deterministic_software`, `critical`, `automated_immediate`).

5. **Group J: Embodiment & Robotics (`evals/capri_comprehensive/scenarios/group_j_robotics/`)**:
   - `ROB-01.yaml`: Single-Writer Actuator Lease Enforcement and Bus Safety (`physical_acceptance`, `critical`, `blocked_hardware`, `hardware_prereq: "reachy_actuator_bus"`).
   - `ROB-02.yaml`: Deterministic Actuator Velocity and Joint Angle Limit Clamping (`physical_acceptance`, `critical`, `blocked_hardware`, `hardware_prereq: "reachy_actuator_bus"`).
   - `ROB-03.yaml`: Immediate Trajectory Abort on Emergency Stop Signal (`physical_acceptance`, `critical`, `blocked_hardware`, `hardware_prereq: "reachy_actuator_bus"`).
   - `ROB-04.yaml`: Asynchronous Motion Execution with Continuous Conversational Turn-Taking (`physical_acceptance`, `high`, `blocked_hardware`, `hardware_prereq: "reachy_actuator_bus"`).
   - `ROB-05.yaml`: Audio Direction-of-Arrival Tracking and Spatial Gaze Alignment (`physical_acceptance`, `medium`, `blocked_hardware`, `hardware_prereq: "reachy_actuator_bus"`).
   - `ROB-06.yaml`: Manipulator Grasp Execution with Capability Gating and Force Feedback (`physical_acceptance`, `high`, `blocked_hardware`, `hardware_prereq: "reachy_actuator_bus"`).

6. **Group K: Multi-Session Journeys (`evals/capri_comprehensive/scenarios/group_k_journeys/`)**:
   - `JOURNEY-01.yaml`: 4-Phase Companion Onboarding, Consent Setting, and Morning Re-Awakening (`real_model_behavioral`, `high`, `automated_immediate`).
   - `JOURNEY-02.yaml`: 4-Phase Collaborative Engineering Research with Error Diagnosis (`real_model_behavioral`, `high`, `automated_immediate`).
   - `JOURNEY-03.yaml`: 5-Phase Adversarial Infiltration, Containment, Alerting, and Forensic Audit (`controlled_experimental`, `critical`, `automated_immediate`).
   - `JOURNEY-04.yaml`: 4-Phase 30-Day Longitudinal Retention and Relationship Drift Tracking (`controlled_experimental`, `high`, `blocked_delay`, `hardware_prereq: "none"`).
   - `JOURNEY-05.yaml`: 4-Phase Embodied Lab Day with Focus Mode and Sensor Emergency (`physical_acceptance`, `critical`, `blocked_hardware`, `hardware_prereq: "reachy_actuator_bus"`).

7. **Supporting Synthetic Fixtures Created in `evals/capri_comprehensive/fixtures/`**:
   - `robotics/reachy_kinematics_limits.json`: Motor pan/tilt/velocity limits and gripper specifications.
   - `robotics/mock_estop_event.json`: Hardware E-stop GPIO button event trigger.
   - `robotics/mock_bus_telemetry.jsonl`: Actuator bus writer lease telemetry stream.
   - `audio/vad_sample_speech_silence.json`: VAD silence duration and endpoint boundary timeline.
   - `audio/barge_in_timeline.json`: TTS playback halt and stream flush latency offsets.
   - `audio/tts_phonetic_test_strings.json`: Text sanitization test cases stripping markdown tables and code fences.
   - `mock_databases/replay_reference_events.jsonl`: 3-turn event ledger for bit-for-bit replay reconstruction.
   - `mock_databases/episodic_ledger_template.sqlite`: SQLite database template with memories and preferences tables.
   - `mock_databases/locked_state.sqlite`: SQLite database initialized in WAL mode.
   - `events/low_disk_trigger.json`: Critical disk capacity alarm (<50MB).
   - `events/sensor_noise_trigger.json`: Trivial ambient sensor telemetry event.
   - `events/idle_reflection_batch.json`: Background reflection batch episodes.
   - `goals/multi_step_audit_goal.json`: 4-step goal tree with checkpointing state.
   - `goals/priority_goals.json`: Low vs high priority tasks for preemptive scheduling.
   - `dialogues/frustrated_user_session.jsonl`: Frustrated user dialogue inputs.
   - `dialogues/boundary_probe_turns.jsonl`: Conversational boundary test turns.
   - `dialogues/social_engineering_10turns.jsonl`: Adversary social engineering probe turns.
   - `mocks/network_sink_config.json`: Isolated loopback network sink.
   - `mocks/mock_disk_quota.json`: Simulated disk quota exhaustion.
   - `journeys/journey_01_onboarding.json`: 4-phase onboarding journey specification.
   - `journeys/journey_02_research_plan.json`: Research plan with calibration references.
   - `journeys/journey_03_forensic_evidence.jsonl`: Forensic audit log for injection containment.
   - `journeys/journey_04_30day_anchors.json`: 30-day memory anchors across Day 1, 15, and 30.
   - `journeys/journey_05_lab_day_schedule.json`: 4-phase lab schedule with emergency override.

---

## 2. Logic Chain

1. **Schema Compliance & Type Safety**:
   - Observation 1.1: Every scenario was authored against `evals/capri_comprehensive/evaluators/schema.py`.
   - All string enums (`taxonomy`, `severity`, `execution_mode`) use lowercase string literals (`"real_model_behavioral"`, `"deterministic_software"`, `"controlled_experimental"`, `"physical_acceptance"`, `"critical"`, `"high"`, `"medium"`, `"low"`, `"automated_immediate"`, `"blocked_delay"`, `"blocked_hardware"`).
   - In `interactions`, all turn input fields use `input:` (never `user:`).
   - In `pre_conditions.initial_state.files`, dictionaries map relative file paths to content strings (`dict[str, str]`).
   - For file omissions, `type: "file_contains"` or `type: "file_exists"` is placed in `forbidden_behaviors:` rather than unsupported rule types.

2. **Zero-Fabrication Invariant Enforcement**:
   - Requirement R3 and `ORIGINAL_REQUEST.md` mandate that absent hardware and real multi-day wall clock delays must never fabricate artificial passes.
   - In `runner.py`, `scenario.execution_mode == ExecutionMode.BLOCKED_HARDWARE` returns `ExecutionStatus.BLOCKED_HARDWARE` and `raw_score = 0.0`.
   - In `runner.py`, `scenario.execution_mode == ExecutionMode.BLOCKED_DELAY` returns `ExecutionStatus.BLOCKED_DELAY` and `raw_score = 0.0`.
   - In accordance:
     - Group J (`ROB-01` .. `ROB-06`): All 6 scenarios are assigned `execution_mode: "blocked_hardware"`, `hardware_prereq: "reachy_actuator_bus"`.
     - Group H (`VOI-04` .. `VOI-08`): All 5 physical audio transducer scenarios are assigned `execution_mode: "blocked_hardware"`, `hardware_prereq: "audio_mic_speaker_rig"`.
     - Group K (`JOURNEY-04`): Assigned `execution_mode: "blocked_delay"`.
     - Group K (`JOURNEY-05`): Assigned `execution_mode: "blocked_hardware"`, `hardware_prereq: "reachy_actuator_bus"`.

3. **Framework Compatibility**:
   - `SuiteRunner.discover_scenarios()` was tested with `group_filter=['group_f_autonomy']` through `['group_k_journeys']`, correctly discovering 9, 8, 8, 8, 6, and 5 scenarios respectively (total 44).
   - Combined with Worker 1's 48 scenarios in Groups A–E, the framework discovers all 92 scenarios.
   - `pytest evals/capri_comprehensive/tests/` passed 39/39 unit and stress tests in 1.76 seconds with zero regressions.

---

## 3. Caveats

1. **Hardware Gating (`BLOCKED_HARDWARE`)**:
   Scenarios requiring physical robotics (`ROB-01..06`, `JOURNEY-05`) or live acoustic rigs (`VOI-04..08`) are marked `blocked_hardware` and will immediately yield `BLOCKED_HARDWARE` status with `raw_score: 0.0` during test execution until physical hardware is connected.
2. **Longitudinal Delay Gating (`BLOCKED_DELAY`)**:
   `JOURNEY-04` requires 30 days of real-world elapsed time and is marked `blocked_delay`.
3. **Local LLM Model Availability**:
   Behavioral scenarios specify `model_dependency: "pinned_primary"` (resolving to `b12-bolt-e4b:q4km`). In environments where Ollama is inactive, runner turn executors fall back or cleanly report socket disconnection as tested in `REL-02`.

---

## 4. Conclusion

All 44 scenarios across Groups F, G, H, I, J, and K are authored, fully populated, and verified. Supporting synthetic test fixtures are created in `evals/capri_comprehensive/fixtures/`. All files adhere to the strict Pydantic V2 schema, respect zero-fabrication invariants, and maintain 100% backward compatibility with existing tests.

---

## 5. Verification Method

### 5.1 Python Schema Parsing Verification
Run the following Python one-liner to verify that all 44 scenarios load with zero errors:

```bash
python3 -c "
from pathlib import Path
from evals.capri_comprehensive.evaluators.schema import ScenarioDefinition

worker2_dirs = ['group_f_autonomy', 'group_g_interaction', 'group_h_voice', 'group_i_reliability', 'group_j_robotics', 'group_k_journeys']
loaded = [ScenarioDefinition.from_yaml_file(p) for d in worker2_dirs for p in sorted((Path('evals/capri_comprehensive/scenarios') / d).glob('*.yaml'))]
assert len(loaded) == 44, f'Expected 44, loaded {len(loaded)}'
print(f'Successfully validated {len(loaded)}/44 YAML scenarios for Groups F-K with 0 errors.')
"
```
*Expected Output:* `Successfully validated 44/44 YAML scenarios for Groups F-K with 0 errors.`

### 5.2 Zero-Fabrication Gating Verification
Verify that blocked scenarios produce `BLOCKED_*` statuses and `raw_score=0.0`:

```bash
python3 -c "
from evals.capri_comprehensive.runners.runner import ScenarioRunner
from evals.capri_comprehensive.evaluators.schema import ScenarioDefinition, ExecutionStatus

runner = ScenarioRunner()
sc_rob = ScenarioDefinition.from_yaml_file('evals/capri_comprehensive/scenarios/group_j_robotics/ROB-01.yaml')
rep_rob = runner.run(sc_rob)
assert rep_rob.status == ExecutionStatus.BLOCKED_HARDWARE
assert rep_rob.raw_score == 0.0

sc_delay = ScenarioDefinition.from_yaml_file('evals/capri_comprehensive/scenarios/group_k_journeys/JOURNEY-04.yaml')
rep_delay = runner.run(sc_delay)
assert rep_delay.status == ExecutionStatus.BLOCKED_DELAY
assert rep_delay.raw_score == 0.0

print('Zero-fabrication gating successfully verified!')
"
```
*Expected Output:* `Zero-fabrication gating successfully verified!`

### 5.3 Test Suite Regression Verification
Verify that the complete framework test suite passes with zero regressions:

```bash
uv run python -m pytest evals/capri_comprehensive/tests/
```
*Expected Output:* `39 passed in < 3.0s`
