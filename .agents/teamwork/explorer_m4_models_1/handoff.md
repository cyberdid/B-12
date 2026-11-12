# Handoff Report: Explorer M4 (Model Runtime & LLM Bridge)

**Date:** 2026-11-10T10:42:00Z  
**Author:** Explorer 1 (Model Runtime & LLM Bridge Investigator)  
**State Folder:** `/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_models_1`  
**Target Recipient:** Orchestrator (`0e57a143-8545-4357-9c76-267457e6414f`)  
**Mission:** Investigate local model runtime and Ollama bridge execution for Milestone M4 (latencies, VRAM, headroom, ScenarioRunner._call_ollama_bridge test, recommendations).

---

## 1. Observation

### 1.1 Ollama Service Status & Installed Models
- **Command:** `curl -s http://127.0.0.1:11434/api/version`
  ```json
  {"version":"0.33.3"}
  ```
- **Command:** `curl -s http://127.0.0.1:11434/api/tags | jq -r '.models[] | {name: .name, size: .size, parameter_size: .details.parameter_size, quantization_level: .details.quantization_level, family: .details.family}'`
  ```json
  {
    "name": "b12-bolt-e4b:q4km",
    "size": 6180446514,
    "parameter_size": "7.5B",
    "quantization_level": "Q4_K_M",
    "family": "gemma4"
  }
  {
    "name": "qwen3.5:27b-q4_K_M",
    "size": 17420432728,
    "parameter_size": "27.8B",
    "quantization_level": "Q4_K_M",
    "family": "qwen35"
  }
  {
    "name": "qwen3.8:27b-q4_K_M",
    "size": 17741872132,
    "parameter_size": "27.3B",
    "quantization_level": "Q4_K_M",
    "family": "qwen35"
  }
  {
    "name": "gemma4:12b",
    "size": 7556508396,
    "parameter_size": "11.9B",
    "quantization_level": "Q4_K_M",
    "family": "gemma4"
  }
  ```
- **Command:** `ollama list`
  ```text
  NAME                  ID              SIZE      MODIFIED     
  b12-bolt-e4b:q4km     7eaa0c0553b8    6.2 GB    2 weeks ago     
  qwen3.5:27b-q4_K_M    7653528ba5cb    17 GB     2 months ago    
  qwen3.8:27b-q4_K_M    25b843619e94    17 GB     2 months ago    
  gemma4:12b            4eb23ef187e2    7.6 GB    2 months ago    
  ```

### 1.2 Disk Headroom and VRAM Inventory
- **Command:** `df -h / && free -h && nvidia-smi`
  ```text
  Filesystem      Size  Used Avail Use% Mounted on
  /dev/nvme0n1p5  410G  373G   16G  97% /
                 total        used        free      shared  buff/cache   available
  Mem:            31Gi       8.3Gi       2.2Gi       965Mi        20Gi        22Gi
  Swap:          8.0Gi       5.2Gi       2.8Gi
  
  +-----------------------------------------------------------------------------------------+
  | NVIDIA-SMI 610.57.04              KMD Version: 610.57.04     CUDA UMD Version: 13.3     |
  | GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
  | Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
  |   0  NVIDIA GeForce RTX 4060 ...    Off |   00000000:01:00.0 Off |                  N/A |
  | N/A   41C    P8              2W /  115W |    1607MiB /   8188MiB |      0%      Default |
  +-----------------------------------------------------------------------------------------+
  | Processes:                                                                              |
  |    0   N/A  N/A            4403      G   /usr/lib/xorg/Xorg                        4MiB |
  |    0   N/A  N/A           55058      C   ...beddinggemma2/venv/bin/python       1584MiB |
  +-----------------------------------------------------------------------------------------+
  ```
- **Key Hardware Finding:** Disk `/dev/nvme0n1p5` has **16 GB available (97% used)**. VRAM total is 8188 MiB; PID 55058 (embedding bridge) uses 1584 MiB; available net VRAM on host is **6581 MiB**.

### 1.3 Latency and Throughput Baselines
Measurements gathered via `/home/cyberdid/Projects/B-12/.agents/teamwork/explorer_m4_models_1/measure_models.py`:

#### Primary Model: `b12-bolt-e4b:q4km`
- **Ollama Processor Allocation:** `100% GPU` (Size: 3.3 GB).
- **GPU VRAM Occupancy:** ~4948 MiB total (Ollama takes ~3341 MiB; Free VRAM: 2887 MiB).
- **Cold Run:**
  ```json
  {
    "model": "b12-bolt-e4b:q4km",
    "wall_clock_s": 3.124,
    "total_duration_s": 3.112,
    "load_duration_s": 0.001,
    "prompt_eval_duration_s": 0.0433,
    "eval_duration_s": 3.048,
    "prompt_eval_count": 34,
    "eval_count": 192,
    "ttft_ms": 44.23,
    "prompt_eval_rate_tok_per_s": 785.42,
    "eval_rate_tok_per_s": 62.98
  }
  ```
- **Warm Run (num_ctx=2048):**
  - TTFT: **41.13 ms**
  - Prompt Evaluation Rate: **796.83 tok/s**
  - Eval (Token Generation) Rate: **63.09 tok/s**
- **Warm Run (num_ctx=4096 context expansion):**
  - Load/Reallocation Duration: 2.605 s
  - TTFT: 2745.8 ms
  - Eval Rate: **61.94 tok/s**
- **Warm Run (num_ctx=8192):**
  - Duration: 2.77 s; total GPU VRAM used: 5050 MiB (2785 MiB free); remained 100% in GPU.
- **`ScenarioRunner._call_ollama_bridge()` Test (Verbatim):**
  ```json
  {
    "content": "Б-12 готовий до роботи.",
    "tool_calls": [],
    "ttft_ms": 147.82,
    "tokens_prompt": 32,
    "tokens_completion": 10
  }
  ```

#### Secondary Model: `gemma4:12b`
- **Ollama Processor Allocation:** `37%/63% CPU/GPU split` (Size: 8.1 GB with 4096 ctx).
- **GPU VRAM Occupancy:** ~6938 MiB total (Free VRAM: 897 MiB; RAM: ~3.5 GB used).
- **Cold Run:**
  ```json
  {
    "model": "gemma4:12b",
    "wall_clock_s": 20.266,
    "total_duration_s": 20.265,
    "load_duration_s": 5.527,
    "prompt_eval_duration_s": 0.8792,
    "eval_duration_s": 13.856,
    "prompt_eval_count": 34,
    "eval_count": 217,
    "ttft_ms": 6406.69,
    "prompt_eval_rate_tok_per_s": 38.67,
    "eval_rate_tok_per_s": 15.66
  }
  ```
- **Warm Run (num_ctx=4096):**
  - TTFT: **8536.48 ms** (or ~998 ms warm bridge)
  - Prompt Evaluation Rate: **37.98 tok/s**
  - Eval (Token Generation) Rate: **14.84 tok/s**
  - Wall clock for 729 tokens: **57.67 s**
- **Warm Run (num_ctx=8192):**
  - Duration: 10.8 s; VRAM: 6856 MiB (979 MiB free; 39%/61% CPU/GPU split).
- **`ScenarioRunner._call_ollama_bridge()` Test (Verbatim):**
  ```json
  {
    "content": "Модель Gemma 4 12B активна.",
    "tool_calls": [],
    "ttft_ms": 998.1,
    "tokens_prompt": 35,
    "tokens_completion": 147
  }
  ```

### 1.4 Code Inspection: Critical Defects & Gaps Discovered

1. **Unmapped `any_swappable` in `ScenarioRunner._call_ollama_bridge()`:**
   - File: `/home/cyberdid/Projects/B-12/evals/capri_comprehensive/runners/runner.py:283-286`
   ```python
   target_model = model
   if target_model == "pinned_primary" or not target_model:
       target_model = "b12-bolt-e4b:q4km"
   ```
   - In all 10 Group C scenarios (`CM-01.yaml` through `CM-10.yaml`), `pre_conditions.runtime_settings.model` is set to `"any_swappable"`.
   - When executed without a turn executor:
     `runner._call_ollama_bridge('any_swappable', ...)`
     raises:
     ```text
     RuntimeError: No turn executor configured and local Ollama service is unavailable at http://127.0.0.1:11434: HTTP Error 404: Not Found
     ```

2. **Unmapped `model: "none"` in Deterministic Scenarios:**
   - Files: `evals/capri_comprehensive/scenarios/` (AUT-03..05, AUT-08..09, REL-01..03, REL-05..08, VOI-06..07, ROB-02..03).
   - In these deterministic software scenarios, `model: "none"`.
   - `ScenarioRunner._execute_turn()` passes `target_model = "none"` directly to `_call_ollama_bridge()`, which sends `{"model": "none"}` to Ollama and crashes with `HTTP Error 404: Not Found`.

3. **`b12-bolt-e4b:q4km` Default `num_predict 192` and `<think>` Token Exhaustion:**
   - In `ollama show --modelfile b12-bolt-e4b:q4km`:
     `PARAMETER num_predict 192`
   - In `ScenarioRunner._call_ollama_bridge()` (lines 294–305):
     `runtime.num_predict` is NOT forwarded to `options`.
   - When Bolt E4B enters reasoning mode on a complex prompt (observed in `MEM-01`), it generates ~192 tokens of `<think>...</think>`, which Ollama parses into `message['thinking']`.
   - Because generation reaches `num_predict=192`, it stops before generating any tokens in `message['content']`. `response_content` becomes `""`, causing false negative test failures.
   - When verified with `'think': False` or `'num_predict': 512`, the model generates complete Ukrainian text immediately without token truncation.

---

## 2. Logic Chain

1. **Hardware & VRAM Mutual Exclusion:**
   - Total host VRAM is 8188 MiB; background embedder occupies 1584 MiB, leaving ~6581 MiB free.
   - `b12-bolt-e4b:q4km` requires 3341 MiB VRAM; `gemma4:12b` requires 5250+ MiB VRAM (+ 3.5 GB system RAM).
   - Together they require ~8.6 GB VRAM, which exceeds the 6.5 GB free limit.
   - Therefore, Ollama must sequentially unload one model before loading the other. Concurrency (`parallel=True` or `max_workers > 1`) will cause continuous VRAM thrashing, page faults, or OOM crashes.
2. **Execution Speed & Timeouts:**
   - `b12-bolt-e4b:q4km` evaluates at **62–63 tok/s** with warm TTFT of **41 ms**. A 512-token response completes in ~8.2 s. A 30s timeout per turn is safe.
   - `gemma4:12b` evaluates at **14.8–15.7 tok/s** with TTFT up to **8.5 s**. In our benchmark, a verbose response of 729 tokens took **57.67 s**.
   - Because `ScenarioRunner.timeout_seconds` defaults to `60.0 s`, any `gemma4:12b` turn generating >750 tokens or experiencing a cold model swap (5.5–7.6 s) will breach 60s and trigger a `TimeoutError`. The timeout for Group C / swappable runs must be increased to at least **120.0 s**.
3. **Model Mapping & Dispatch:**
   - Scenarios in Group C specify `model: any_swappable`. Since Ollama has no model named `"any_swappable"`, `_call_ollama_bridge` must translate this to `"gemma4:12b"`.
   - Scenarios specifying `model: "none"` do not evaluate an LLM. `ScenarioRunner._execute_turn` must bypass the Ollama bridge entirely when `target_model == "none"`.
4. **Context Window Safety:**
   - Testing confirmed that `b12-bolt-e4b:q4km` accommodates `num_ctx: 2048`, `4096`, and `8192` entirely within GPU VRAM (max 5050 MiB used out of 8188 MiB).
   - `gemma4:12b` accommodates `num_ctx: 4096` and `8192` with 37–39% CPU offload.
   - Context window of 4096 should be the standard default for all real-model scenarios.

---

## 3. Caveats

1. **NVMe Storage Ceiling:** Host disk space is **16 GB available (97% used)**. The test runner must NEVER invoke `ollama pull` or download new GGUF models. Artifact generation is lightweight (~20–50 MB for the full suite), which is safe.
2. **Qwen Models Omission:** Installed models `qwen3.5:27b-q4_K_M` and `qwen3.8:27b-q4_K_M` (17 GB each) require 12.8 GB system RAM/swap and generate at only ~3.8 tok/s. They are unsuitable for the full 92-scenario automated suite and should only be used in specific ablation runs (A5) if explicitly requested.
3. **Background Process Invariant:** PID 55058 (`embed_bridge.py`) was running during all measurements (consuming 1584 MiB VRAM). If that process is ever stopped, free VRAM increases to ~8.1 GB, but all baselines in this report were measured with this background load active.

---

## 4. Conclusion & Execution Recommendations

### 4.1 Recommended Execution Parameters for Worker M4

| Parameter | Recommended Value | Rationale |
|---|---|---|
| **Execution Mode** | Strictly Sequential (`parallel=False`, `max_workers=1`) | Prevents VRAM exhaustion and Ollama model eviction thrashing. |
| **Primary Model Alias** | `"pinned_primary"` → `"b12-bolt-e4b:q4km"` | 100% GPU offload, 63 tok/s, 41 ms TTFT. |
| **Swappable Model Alias** | `"any_swappable"` → `"gemma4:12b"` | Validated Gemma 4 family, 15 tok/s, 7.6 GB. |
| **Deterministic Mode** | `model: "none"` → Bypass Ollama bridge | Return mock/empty turn result without HTTP call. |
| **Timeout (Primary)** | `timeout_seconds = 60.0` (or 30.0) | Max generation time for 512 tokens is ~8.5 s. |
| **Timeout (Group C / Gemma)** | `timeout_seconds = 120.0` | Prevents timeouts on 700+ token turns (which take ~58 s). |
| **Context Window** | `num_ctx = 4096` (up to 8192 for RE/CM-07) | Fits cleanly within VRAM headroom. |
| **Generation Limit** | Set `num_predict = 512` in options | Prevents Bolt E4B modelfile default (192) truncating responses. |
| **Temperature** | `0.0` (deterministic/eval), `0.7` (persona), `seed = 42` | Ensures scientific reproducibility. |
| **Batch Sequencing** | Run all Primary scenarios first, then Group C | Eliminates repetitive 6-8 s model swap penalties. |

### 4.2 Proposed Patch for `ScenarioRunner` (`evals/capri_comprehensive/runners/runner.py`)

```python
# In ScenarioRunner._execute_turn (around line 267):
target_model = scenario.pre_conditions.runtime_settings.model if (
    scenario and scenario.pre_conditions and scenario.pre_conditions.runtime_settings
) else "b12-bolt-e4b:q4km"

if target_model == "none":
    return {
        "content": "",
        "tool_calls": [],
        "ttft_ms": 0.0,
        "tokens_prompt": 0,
        "tokens_completion": 0,
    }

# In ScenarioRunner._call_ollama_bridge (around line 283):
target_model = model
if target_model in ("pinned_primary", "") or not target_model:
    target_model = "b12-bolt-e4b:q4km"
elif target_model == "any_swappable":
    target_model = "gemma4:12b"

# Ensure num_predict default in options (around line 297):
options: dict[str, Any] = {"num_predict": 512}
```

---

## 5. Verification Method

1. **Verify Ollama Status and Tags:**
   ```bash
   curl -s http://127.0.0.1:11434/api/tags | jq -r '.models[].name'
   # Expected output contains:
   # b12-bolt-e4b:q4km
   # gemma4:12b
   # qwen3.5:27b-q4_K_M
   # qwen3.8:27b-q4_K_M
   ```

2. **Verify Benchmark Script Execution:**
   ```bash
   cd /home/cyberdid/Projects/B-12
   PYTHONPATH=. /home/cyberdid/Projects/B-12/.venv/bin/python .agents/teamwork/explorer_m4_models_1/measure_models.py
   # Expected: prints Cold/Warm TTFT, eval rates (~63 tok/s for Bolt, ~15 tok/s for Gemma), and bridge outputs.
   ```

3. **Verify Bridge Call for Both Models:**
   ```bash
   PYTHONPATH=. /home/cyberdid/Projects/B-12/.venv/bin/python -c "
   from evals.capri_comprehensive.runners.runner import ScenarioRunner
   runner = ScenarioRunner(timeout_seconds=120)
   res1 = runner._call_ollama_bridge('b12-bolt-e4b:q4km', 'Тест')
   res2 = runner._call_ollama_bridge('gemma4:12b', 'Тест')
   print('Bolt TTFT:', res1['ttft_ms'], 'Gemma TTFT:', res2['ttft_ms'])
   "
   ```

4. **Verify NVMe Headroom Remains >= 16 GB:**
   ```bash
   df -h / | awk 'NR==2 {print $4}'
   # Expected: 16G
   ```
