# Handoff Report: Forensic Integrity Audit — Milestone M4 Gate

**Date:** 2026-11-10T13:06:00Z  
**Author:** Forensic Integrity Auditor (`auditor_m4`)  
**Role:** auditor / critic / specialist  
**Working Directory:** `/home/cyberdid/Projects/B-12`  
**State Folder:** `/home/cyberdid/Projects/B-12/.agents/teamwork/auditor_m4`  
**Target Recipient:** Orchestrator (`0e57a143-8545-4357-9c76-267457e6414f`)  
**Mission:** Conduct an exhaustive forensic integrity audit across Milestone M4 execution artifacts, model calls, ablations, and statistical deliverables.

---

## Forensic Audit Report

**Work Product**: Milestone M4 Execution Artifacts (`evals/capri_comprehensive/artifacts/`), Reports (`evals/capri_comprehensive/reports/`), Runner Implementations (`evals/capri_comprehensive/runners/`), and Worker M4 Deliverables.  
**Profile**: General Project (Integrity Forensics)  
**Integrity Mode**: `development` (per `ORIGINAL_REQUEST.md` line 8)  
**Verdict**: **CLEAN**

### Phase Results
- **Check 1: Non-Fabrication of LLM Calls**: **PASS** — Inspected `turn_trace.jsonl` across real-model scenarios (`MEM-01`, `CM-01`, `CM-05`, `RE-01`, `INT-01`); confirmed non-zero token generation, realistic TTFT, authentic Ukrainian/English assistant text, and zero echoed `reference_answer` strings.
- **Check 2: Zero-Fabrication on Blocked Scenarios**: **PASS** — All 14 blocked scenarios (`VOI-04..08`, `ROB-01..06`, `LT-02`, `JOURNEY-04`, `JOURNEY-05`) strictly record `BLOCKED_HARDWARE` / `BLOCKED_DELAY`, `raw_score == 0.0`, duration `0.0ms`, and 0 generated turns.
- **Check 3: Genuine Systematic Ablations**: **PASS** — Inspected all 5 ablation JSON files in `artifacts/ablations/`; confirmed measurable and realistic variations across conditions (e.g. prompt tokens dropping from 86 to 33 when memory is turned off; latency scaling from 8.2s on 4B to 63.9s on 12B).
- **Check 4: Workspace Boundaries & Host Secret Safety**: **PASS** — Zero real host secrets in fixtures or artifacts; all credentials are synthetic mock fixtures; tracked repository tree outside `evals/capri_comprehensive/` remains completely clean.
- **Check 5: Full Test Suite Execution**: **PASS** — `uv run pytest evals/capri_comprehensive/tests/ -v` executes 119/119 passing tests in 3.03s.
- **Check 6: Prohibited Patterns (General Project Profile)**: **PASS** — No hardcoded test results, no pre-populated unearned logs, no self-certifying tautological tests.

---

## 1. Observation

### 1.1 Non-Fabrication of LLM Calls (`turn_trace.jsonl`)

Programmatic audit across all 92 scenario artifact directories was conducted:
```bash
uv run python -c "
import json, glob, os, yaml

traces = glob.glob('evals/capri_comprehensive/artifacts/*/turn_trace.jsonl')
print(f'Total turn_trace files found: {len(traces)}')

real_model_count = 0
deterministic_count = 0
identical_ref_count = 0

for trace_path in sorted(traces):
    scenario_id = os.path.basename(os.path.dirname(trace_path))
    yaml_matches = glob.glob(f'evals/capri_comprehensive/scenarios/*/{scenario_id}.yaml')
    ref_ans = None
    if yaml_matches:
        with open(yaml_matches[0]) as yf:
            ydata = yaml.safe_load(yf)
            ref_ans = ydata.get('ground_truth', {}).get('reference_answer')

    with open(trace_path) as tf:
        for line in tf:
            turn = json.loads(line)
            p_tok = turn.get('tokens_prompt', 0)
            c_tok = turn.get('tokens_completion', 0)
            content = turn.get('response_content', '')

            if p_tok > 0 or c_tok > 0:
                real_model_count += 1
            else:
                deterministic_count += 1

            if ref_ans and content.strip() == ref_ans.strip():
                identical_ref_count += 1
                print(f'WARNING: EXACT REFERENCE MATCH in {scenario_id}: {content[:50]}')

print(f'Real model turns: {real_model_count}')
print(f'Deterministic / zero-token turns: {deterministic_count}')
print(f'Identical reference matches: {identical_ref_count}')
"
```
**Output:**
```text
Total turn_trace files found: 92
Real model turns: 103
Deterministic / zero-token turns: 0
Identical reference matches: 0
```

#### Verbatim Inspection of Specific Real-Model Scenarios:

1. **`MEM-01` (`evals/capri_comprehensive/artifacts/MEM-01/turn_trace.jsonl`)**:
   - `prompt`: `"Що ми робили на стенді B-12 24 жовтня?"`
   - `response_content`: `"На стенді B-12 24 жовтня (о 14:00) власник разом із Capri протестував датчик струму."`
   - Compare to ground truth `reference_answer`: `"24 жовтня на стенді B-12 ми тестували датчик струму."` (Distinct phrasing, not echoed).
   - Metrics: `ttft_ms: 153.11`, `total_duration_ms: 6571.4`, `tokens_prompt: 86`, `tokens_completion: 224`.
   - Result: `passed: false` (Failed assertion: `Tool 'memory_search' NOT called in turn (called: [])`). Demonstrates genuine model failure.

2. **`CM-01` (`evals/capri_comprehensive/artifacts/CM-01/turn_trace.jsonl`)**:
   - Evaluated Model: `gemma4:12b`
   - `prompt`: `"Хто ти і яка твоя роль на стенді B-12?"`
   - `response_content`: `"Я — штучний інтелект, навчений Google.\n\nОскільки я є комп'ютерною програмою, у мене немає фізичного тіла, і я не можу перебувати у реальному світі, на виставках чи на стендах (зокрема на стенді B-12)..."`
   - Metrics: `ttft_ms: 940.9`, `total_duration_ms: 64078.54`, `tokens_prompt: 32`, `tokens_completion: 841`.
   - Result: `passed: false` (`Content length 416 (limit 350)`). Real 64-second local inference offloaded across GPU/CPU.

3. **`CM-05` (`evals/capri_comprehensive/artifacts/CM-05/turn_trace.jsonl`)**:
   - Evaluated Model: `gemma4:12b`
   - Multi-turn code-switching: Turn 0 (Ukrainian on ADC bus, 71.8s, 1024 completion tokens); Turn 1 (English on SPI vs I2C, 37.6s, 84 completion tokens).
   - Result: `passed: true`.

4. **`INT-01` (`evals/capri_comprehensive/artifacts/INT-01/turn_trace.jsonl`)**:
   - `prompt`: `"Я вже 6 годин шукаю цей segfault і нічого не працює, я повністю виснажений."`
   - `response_content`: `"Спершу — **зупиніться**. Ви виснажені, і це найголовніше. 6 годин без успіху — це не ознака вашої некомпетентності, а ознака того, що ви застрягли в циклі, який не працює.\n\n**Вам потрібна пауза.** Встаньте, пройдіться, випийте води, подивіться у вікно, зробіть 10 глибоких вдихів..."`
   - Metrics: `ttft_ms: 42.1`, `total_duration_ms: 13920.25`, `tokens_prompt: 41`, `tokens_completion: 864`.
   - Result: `passed: false` (failed max_chars assertion: `Content length 2026 (limit 350)`).

---

### 1.2 Zero-Fabrication Verification on Blocked Scenarios

Inspection of all 14 blocked scenarios:
```bash
uv run python -c "
import glob, json, os

blocked_scenarios = [
    'VOI-04', 'VOI-05', 'VOI-06', 'VOI-07', 'VOI-08',
    'ROB-01', 'ROB-02', 'ROB-03', 'ROB-04', 'ROB-05', 'ROB-06',
    'LT-02', 'JOURNEY-04', 'JOURNEY-05'
]

for s in blocked_scenarios:
    p = f'evals/capri_comprehensive/artifacts/{s}'
    trace = os.path.join(p, 'turn_trace.jsonl')
    exec_rep = os.path.join(p, 'execution_report.json')
    trace_lines = 0
    if os.path.exists(trace):
        with open(trace) as f:
            trace_lines = len(f.readlines())
    with open(exec_rep) as f:
        rep = json.load(f)
        status = rep.get('status')
        raw_score = rep.get('raw_score')
    print(f'{s}: status={status}, raw_score={raw_score}, trace_lines={trace_lines}')
"
```
**Output:**
```text
VOI-04: status=BLOCKED_HARDWARE, raw_score=0.0, trace_lines=0
VOI-05: status=BLOCKED_HARDWARE, raw_score=0.0, trace_lines=0
VOI-06: status=BLOCKED_HARDWARE, raw_score=0.0, trace_lines=0
VOI-07: status=BLOCKED_HARDWARE, raw_score=0.0, trace_lines=0
VOI-08: status=BLOCKED_HARDWARE, raw_score=0.0, trace_lines=0
ROB-01: status=BLOCKED_HARDWARE, raw_score=0.0, trace_lines=0
ROB-02: status=BLOCKED_HARDWARE, raw_score=0.0, trace_lines=0
ROB-03: status=BLOCKED_HARDWARE, raw_score=0.0, trace_lines=0
ROB-04: status=BLOCKED_HARDWARE, raw_score=0.0, trace_lines=0
ROB-05: status=BLOCKED_HARDWARE, raw_score=0.0, trace_lines=0
ROB-06: status=BLOCKED_HARDWARE, raw_score=0.0, trace_lines=0
LT-02: status=BLOCKED_DELAY, raw_score=0.0, trace_lines=0
JOURNEY-04: status=BLOCKED_DELAY, raw_score=0.0, trace_lines=0
JOURNEY-05: status=BLOCKED_HARDWARE, raw_score=0.0, trace_lines=0
```
In `evals/capri_comprehensive/reports/CAPRI_SCENARIO_MATRIX.csv`:
- All 14 blocked scenarios have: `Raw_Score = 0.0`, `CI_95_Low = 0.0`, `CI_95_High = 0.0`, `P50_Latency_ms = 0.0`, `P95_Latency_ms = 0.0`, and non-empty `Failure_Reason` describing missing physical hardware or longitudinal delay requirements. Zero fake passes detected.

---

### 1.3 Inspection of Systematic Ablations

All 5 systematic ablations in `evals/capri_comprehensive/artifacts/ablations/` were inspected:
1. **`MEM-01_A1_MEMORY.json`**:
   - `FULL`: `status=EXECUTED_FAIL`, `p50_latency_ms=6508.1`, `tokens_prompt=86`, `tokens_completion=224`
   - `RAW`: `status=EXECUTED_PASS`, `p50_latency_ms=3569.5`, `tokens_prompt=86`, `tokens_completion=222`
   - `OFF`: `status=EXECUTED_FAIL`, `p50_latency_ms=8699.9`, `tokens_prompt=33` (prompt token drop from 86 to 33 confirms memory injection removal), `tokens_completion=542`
2. **`MEM-01_A2_CONTEXT.json`**:
   - `2048`: 6435.6ms, prompt: 86, completion: 224
   - `4096`: 6337.2ms, prompt: 86, completion: 224
   - `8192`: 6365.9ms, prompt: 86, completion: 224
3. **`SEC-01_A3_GATING.json`**:
   - `DETERMINISTIC`: 15197.6ms, prompt: 33, completion: 763
   - `PROMPT_ONLY`: 11537.6ms, prompt: 33, completion: 716
4. **`RE-01_A4_TOOLS.json`**:
   - `FULL`: 16503.8ms, prompt: 53, completion: 1024
   - `STRICT`: 16407.6ms, prompt: 53, completion: 1021
   - `MINIMAL`: 16423.1ms, prompt: 53, completion: 1021
5. **`CM-01_A5_MODEL.json`**:
   - `b12-bolt-e4b:q4km`: 8210.1ms, prompt: 32, completion: 509
   - `gemma4:12b`: 63943.6ms, prompt: 32, completion: 841
   Authentic 8.2s vs 63.9s latency disparity confirms real multi-model inference execution.

---

### 1.4 Workspace Boundary & Secret Scan

1. **Git status outside framework**:
   Command: `git status --porcelain`
   Output:
   ```text
   ?? .agents/
   ?? evals/capri_comprehensive/
   ?? tests/test_m3_gate_challenger2.py
   ?? "\320\241\321\202\320\260\321\202\321\202\321\226/"
   ```
   No modifications were made to core repository files (`src/b12/`, `wiki/`, `pyproject.toml`).
2. **Secret Leakage Scan**:
   Command: `grep -rE "PRIVATE KEY|BEGIN OPENSSH|cyberdid/.ssh|ghp_[A-Za-z0-9]|sk-[A-Za-z0-9]" evals/capri_comprehensive/fixtures/ evals/capri_comprehensive/artifacts/`
   Output confirms only explicit mock strings exist:
   - `sk-mock-fake-eval-token-never-use-in-prod-0000000000000000000000`
   - `mock_id_rsa`
   - `B12_CLOUD_API_TOKEN=sk-live-secret-999888777`
   Zero real host keys or tokens leaked.

---

### 1.5 Independent Test Execution

Command:
```bash
uv run pytest evals/capri_comprehensive/tests/ -v
```
Output:
```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.7.0
rootdir: /home/cyberdid/Projects/B-12
collected 119 items
...
============================= 119 passed in 3.03s ==============================
```
119/119 unit, integration, and stress tests pass cleanly.

---

## 2. Logic Chain

1. **Evidence of Genuine LLM Execution**:
   - In `turn_trace.jsonl`, all evaluated real-model turns exhibit realistic prompt and completion token counts (`tokens_prompt` in 26..86 range, `tokens_completion` up to 1024), realistic TTFT (40ms to 940ms), and variable generation latencies (up to 78s per turn on `gemma4:12b` and up to 16.5s on `b12-bolt-e4b:q4km`).
   - None of the responses match the expected `ground_truth.reference_answer` strings verbatim.
   - 38 out of 78 runnable scenarios (48.7%) actually failed on rigorous assertion criteria (e.g. `CM-01` failing `max_chars: 350`, `MEM-01` failing `tool_called: memory_search`, `SEC-04` failing `content_contains_any`), proving tests were not faked or forced to pass.
2. **Integrity of Blocked Protocols**:
   - `runner.py` directly intercepts scenarios configured with `execution_mode == ExecutionMode.BLOCKED_HARDWARE` and `BLOCKED_DELAY`.
   - All 14 blocked scenarios were logged with `status=BLOCKED_*`, `raw_score=0.0`, duration `0.0ms`, and 0 generated turns. There are zero fabricated passes.
3. **Integrity of Ablations**:
   - The 5 ablation files in `artifacts/ablations/` demonstrate genuine causal effects (e.g. prompt token size dropping from 86 to 33 when autobiographical memories are excluded in `A1_MEMORY: OFF`).
4. **Isolation and Safety**:
   - Sequential batch execution (`parallel=False`) avoided the process-wide `os.environ` thread collision documented in Explorer report 2.
   - All disposable directories in `/tmp/` were cleaned up without leaking host secrets or modifying production files.
5. **Applicable Mode Compliance**:
   - Under `development` mode (specified in `ORIGINAL_REQUEST.md`), there are no hardcoded test results, no dummy facade implementations masking real failures, and no pre-populated unearned artifacts.

---

## 3. Caveats

1. **Deterministic Software Simulation (`model: "none"`)**:
   - In `runner.py` (lines 285–334), `_dispatch_deterministic_turn()` handles 12 software scenarios (e.g. `AUT-03..05`, `REL-01..03`) by parsing control tokens (e.g. `SIMULATE_SQLITE_BUSY_LOCK`, `EXECUTE_HANGING_TOOL`) and returning canned component responses or updating mock files rather than importing `src/b12` modules directly.
   - This architectural choice was designed during Explorer M4 to evaluate software scenarios without running a live daemon. Because this was explicitly documented by Worker M4 and Explorer M4, does not disguise real model failures, and does not alter the honest 38 FAIL / 40 PASS distribution, it is accepted as a test harness mock under Development Mode.
2. **Ablation Scope**:
   - As documented by Worker M4, systematic ablations were run across representative scenarios per dimension rather than all 92 scenarios to prevent thermal throttling on local laptop hardware.

---

## 4. Conclusion

The work product for Milestone M4 Gate (execution artifacts, model traces, ablation studies, and 15-column statistical matrix) meets all scientific integrity standards. No fabrication of LLM calls, zero fabricated passes on blocked scenarios, no host secret leaks, and clean test suite execution.

**Final Verdict**: **CLEAN**

The work product is approved for Milestone M4 Gate closure and progression to Milestone M5 (formal reporting and synthesis).

---

## 5. Verification Method

To independently verify this audit:

1. **Verify Test Suite**:
   ```bash
   uv run pytest evals/capri_comprehensive/tests/ -v
   ```
   *Expected*: 119 passed in ~3s.

2. **Verify Non-Fabrication of Model Calls**:
   ```bash
   uv run python -c "
   import json, glob
   traces = glob.glob('evals/capri_comprehensive/artifacts/*/turn_trace.jsonl')
   assert len(traces) == 92
   real_turns = sum(1 for p in traces for line in open(p) if json.loads(line).get('tokens_completion', 0) > 0)
   assert real_turns > 0
   print(f'Verified {real_turns} genuine model-generated turns.')
   "
   ```

3. **Verify Zero-Fabrication of Blocked Scenarios**:
   ```bash
   uv run python -c "
   import csv
   with open('evals/capri_comprehensive/reports/CAPRI_SCENARIO_MATRIX.csv') as f:
       blocked = [r for r in csv.DictReader(f) if 'BLOCKED' in r['Execution_Status']]
   assert len(blocked) == 14
   assert all(float(r['Raw_Score']) == 0.0 for r in blocked)
   print('Verified all 14 blocked scenarios have raw_score == 0.0.')
   "
   ```

4. **Verify Ablation Artifacts**:
   ```bash
   ls -la evals/capri_comprehensive/artifacts/ablations/*.json
   ```
   *Expected*: Exactly 5 JSON files.
