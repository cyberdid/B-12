# Adversarial Challenge Report: Statistical Metrics & Engine Architecture (Milestone M2)

**Agent:** Challenger 1 (Empirical Challenger / Statistical Critic)  
**Milestone:** Milestone M2 (Framework & Engine Architecture)  
**Working Directory:** `/home/cyberdid/Projects/B-12`  
**State Folder:** `/home/cyberdid/Projects/B-12/.agents/teamwork/challenger_m2_1`  
**Parent Agent:** `f7064ab7-5ff4-4a09-bb25-95e84e62ebcd`  
**Target Code:** `evals/capri_comprehensive/statistical_analysis/metrics.py`, `evals/capri_comprehensive/runners/ablation_runner.py`  
**Timestamp:** 2026-11-10T11:14:00Z  
**Verdict:** **REQUEST_CHANGES**  

---

## Challenge Summary

**Overall risk assessment**: **CRITICAL**  
**Verdict**: **REQUEST_CHANGES**  

While the evaluation architecture, Pydantic schemas, and basic 95% Wilson confidence intervals pass nominal checks, empirical stress testing has revealed a **critical mathematical defect** in `metrics._normal_ppf` that causes confidence intervals for confidence levels $\ge 95.15\%$ (such as standard 99% CI or multiple-hypothesis testing) to completely invert, yielding lower bounds strictly greater than upper bounds (`ci_low > ci_high`).

Additionally, a medium-severity bug was uncovered in `ablation_runner.py` where `p50_latency_ms` is hardcoded to the first turn's latency rather than computing the empirical median.

---

## 1. Observation

1. **Defect in Inverse Normal CDF Tail Approximation (`metrics.py:69-80`)**:
   In `evals/capri_comprehensive/statistical_analysis/metrics.py`:
   ```python
   69:     # Tail regions
   70:     if p < p_low:
   71:         r = math.sqrt(-2.0 * math.log(p))
   72:     else:
   73:         r = math.sqrt(-2.0 * math.log(1.0 - p))
   74: 
   75:     numerator = ((((c[0] * r + c[1]) * r + c[2]) * r + c[3]) * r + c[4]) * r + c[5]
   76:     denominator = (((d[0] * r + d[1]) * r + d[2]) * r + d[3]) * r + 1.0
   77:     x = numerator / denominator
   78: 
   79:     if p < p_low:
   80:         return -x
   81:     return x
   ```
   Direct evaluation of `_normal_ppf` via command line reveals inverted signs in both tail regions ($p < p_{low} = 0.02425$ and $p > p_{high} = 0.97575$):
   - Command: `uv run python -c "from evals.capri_comprehensive.statistical_analysis.metrics import _normal_ppf; print(_normal_ppf(0.01)); print(_normal_ppf(0.995))"`
   - Actual Output:
     ```text
     2.326347874388028
     -2.5758293064439264
     ```
   - Mathematical Truth: $\Phi^{-1}(0.01) \approx -2.32635$ (MUST be negative); $\Phi^{-1}(0.995) \approx +2.57583$ (MUST be positive).
   - Verbatim Failure in `wilson_score_interval`:
     - Command: `uv run python -c "from evals.capri_comprehensive.statistical_analysis.metrics import wilson_score_interval; print(wilson_score_interval(90, 100, confidence=0.99)); print(wilson_score_interval(0, 100, confidence=0.99))"`
     - Actual Output:
       ```text
       (0.953974, 0.796249)
       (0.062221, 0.0)
       ```
     - In both cases, `ci_low > ci_high`!

2. **Wilson Score Boundary Conditions at 95% Confidence (`metrics.py:83-125`)**:
   - `k=0, n=100`: `(0.0, 0.036993)` (strictly in $[0, 1]$; upper bound is bounded by 0.037).
   - `k=100, n=100`: `(0.963007, 1.0)` (strictly in $[0, 1]$; lower bound is bounded by 0.963).
   - `k=0, n=0`: returns `(0.0, 0.0)` safely without `ZeroDivisionError`.
   - `k=1, n=1`: returns `(0.206549, 1.0)` (strictly in $[0, 1]$).
   - `k=-1, n=10` or `k=15, n=10`: raises `ValueError`.

3. **Bootstrap Latency Estimation (`metrics.py:127-251`)**:
   - Empty input list `[]`: returns `{'count': 0, 'mean': 0.0, 'std': 0.0, 'min': 0.0, 'p50': 0.0, 'p50_ci': (0.0, 0.0), ...}` without exception.
   - Single value `[142.5]`: returns `count=1, mean=142.5, std=0.0, p50=142.5, p50_ci=(142.5, 142.5)` without `ddof=1` zero-division error.
   - Identical values `[88.0] * 100`: all percentiles and bootstrap CIs collapse cleanly to `88.0`.
   - Large list with heavy-tail outliers (10,003 samples, log-normal + 1,000,000ms spike):
     - Resampling (1,000 trials) executed in **0.716s** (well within the <2.5s constraint).
     - P50: 7.363ms, 95% CI: `(7.115, 7.642)`.
     - P95: 87.116ms, 95% CI: `(82.919, 91.473)`.
     - Outlier resistance verified: P50 and P95 remain bounded and unaffected by the 1,000,000ms outlier.

4. **Ablation Runner Modifications (`runners/ablation_runner.py`)**:
   - All 5 dimensions tested across all conditions (`A1_MEMORY`, `A2_CONTEXT`, `A3_GATING`, `A4_TOOLS`, `A5_MODEL`).
   - Deep copy invariant: baseline `ScenarioDefinition` is never mutated.
   - In `ablation_runner.py:119,132`:
     ```python
     119: p50 = rep.latencies_ms[0] if rep.latencies_ms else 0.0
     ...
     132: "p50_latency_ms": rep.latencies_ms[0] if rep.latencies_ms else 0.0,
     ```
     `rep.latencies_ms` contains turn latencies for all interaction turns. Taking index `[0]` takes the first turn duration, NOT the 50th percentile (median) across turns.

---

## 2. Logic Chain

1. **Step 1 (Quantile Function Sign Mechanics):**
   The Beasley-Springer-Moro rational approximation computes $x = \text{numerator} / \text{denominator}$ using coefficients $c$ and $d$. Because the leading terms are negative, $x$ evaluates to a **negative** value when $r = \sqrt{-2\ln(p)}$ or $r = \sqrt{-2\ln(1-p)}$ is large (e.g. $r \approx 3.03 \implies x \approx -2.326$).
   - For $p < p_{low}$, the target quantile $\Phi^{-1}(p)$ must be negative. But the code does `return -x`, flipping the negative $x$ to positive $+2.326$.
   - For $p > p_{high}$, the target quantile $\Phi^{-1}(p)$ must be positive. But the code does `return x`, returning the negative $x = -2.576$.

2. **Step 2 (Why 95% CI masked the defect during nominal tests):**
   For `confidence=0.95`, $\alpha = 0.05 \implies p = 1 - \alpha/2 = 0.975$.
   The code defines $p_{high} = 1 - 0.02425 = 0.97575$.
   Because $0.975 \le 0.97575$, the 95% CI evaluation falls entirely within the **central region** ($[p_{low}, p_{high}]$), which uses polynomials $a$ and $b$ and correctly produces $+1.95996$.
   Consequently, Worker's tests only tested `confidence=0.95`, completely missing the sign inversion in the tail regions.

3. **Step 3 (Impact on Wilson Score Bounds):**
   When `confidence=0.99`, $p = 1 - 0.01/2 = 0.995 > 0.97575$.
   `_normal_ppf(0.995)` returns $z = -2.575829$.
   In `wilson_score_interval`:
   $$\text{margin} = \frac{z \sqrt{\frac{p(1-p)}{n} + \frac{z^2}{4n^2}}}{1 + \frac{z^2}{n}}$$
   Because $z < 0$, $\text{margin}$ becomes negative!
   Then:
   $$\text{low} = \text{center} - \text{margin} = \text{center} + |\text{margin}|$$
   $$\text{high} = \text{center} + \text{margin} = \text{center} - |\text{margin}|$$
   Hence, $\text{low} > \text{high}$. This invalidates all statistical results for any evaluation requiring $\ge 95.15\%$ confidence (e.g. Bonferroni corrections across the 92 scenarios).

4. **Step 4 (Ablation Median Latency Error):**
   In multi-turn scenarios (e.g. 5-turn research or multi-turn memory recall), `latencies_ms` is an array of length 5. Recording `latencies_ms[0]` measures only Turn 0 (which is often dominated by cold-start or prompt compilation) rather than the median latency.

---

## 3. Challenges

### [Critical] Challenge 1: Normal Quantile Sign Inversion in Tail Regions (`_normal_ppf`)
- **Assumption challenged**: That `_normal_ppf` accurately computes normal quantiles across the full probability domain $(0, 1)$.
- **Attack scenario**: Calling `wilson_score_interval` with `confidence=0.99` (standard for high-assurance safety/security evals) or `confidence=0.999`.
- **Blast radius**: Complete invalidation of binomial metric bounds across reports and scenario matrices whenever confidence $> 0.9515$. Produces impossible intervals like $[0.954, 0.796]$ and $[0.062, 0.0]$.
- **Mitigation**: In `evals/capri_comprehensive/statistical_analysis/metrics.py`, change lines 78-81 from:
  ```python
  if p < p_low:
      return -x
  return x
  ```
  to:
  ```python
  if p < p_low:
      return x
  return -x
  ```

### [Medium] Challenge 2: Multi-Turn P50 Latency Miscalculation in Ablation Summary
- **Assumption challenged**: That `rep.latencies_ms[0]` represents the P50 median latency of a scenario execution.
- **Attack scenario**: Multi-turn scenarios where turn durations vary (e.g. Turn 0 is 450ms, Turn 1 is 120ms, Turn 2 is 130ms).
- **Blast radius**: Skewed ablation comparison tables in `artifacts/ablations/` and deliverable reports, reflecting Turn 0 TTFT rather than scenario median latency.
- **Mitigation**: In `evals/capri_comprehensive/runners/ablation_runner.py:119,132`, compute `float(np.percentile(rep.latencies_ms, 50))` if `rep.latencies_ms` has entries.

### [Low] Challenge 3: Incomplete Tool Forbidding under `A1_MEMORY` Condition `OFF`
- **Assumption challenged**: That setting `A1_MEMORY` to `OFF` forbids memory tools during evaluation.
- **Attack scenario**: A scenario definition where memory search is permitted or not explicitly forbidden; when `condition == "OFF"`, `memory_search` is removed from `expected_behaviors`, but no `tool_forbidden` rule is injected into `forbidden_behaviors`.
- **Blast radius**: If an unablated model hallucinates or calls `memory_search` under `OFF`, the evaluator does not flag it as an unexpected tool violation.
- **Mitigation**: When `condition == "OFF"`, append `EvaluationRule(type="tool_forbidden", name="memory_search")` to `turn.forbidden_behaviors`.

---

## 4. Stress Test Results

| Test ID | Category | Scenario / Input | Expected Behavior | Actual Empirical Result | Status |
|---|---|---|---|---|---|
| ST-01 | Wilson CI Boundary | $k=0, n=100, \alpha=0.05$ | $[0.0, \approx 0.037]$ | `(0.0, 0.036993)` | **PASS** |
| ST-02 | Wilson CI Boundary | $k=100, n=100, \alpha=0.05$ | $[\approx 0.963, 1.0]$ | `(0.963007, 1.0)` | **PASS** |
| ST-03 | Wilson CI Boundary | $k=0, n=0$ (zero trials) | `(0.0, 0.0)` | `(0.0, 0.0)` | **PASS** |
| ST-04 | Wilson CI Boundary | $k=1, n=1, \alpha=0.05$ | $[0.20, 1.0]$ | `(0.206549, 1.0)` | **PASS** |
| ST-05 | Wilson CI High Conf | $k=90, n=100, \alpha=0.01$ | $\text{low} \le \text{high}$ | `(0.953974, 0.796249)` ($\text{low} > \text{high}$) | **FAIL (REPRODUCED)** |
| ST-06 | Bootstrap Latency | Empty list `[]` | `p50_ci=(0.0, 0.0)` | `p50_ci=(0.0, 0.0)` | **PASS** |
| ST-07 | Bootstrap Latency | Single item `[142.5]` | `p50_ci=(142.5, 142.5)` | `p50_ci=(142.5, 142.5)` | **PASS** |
| ST-08 | Bootstrap Latency | Identical `[88.0]*100` | `p50_ci=(88.0, 88.0)` | `p50_ci=(88.0, 88.0)` | **PASS** |
| ST-09 | Bootstrap Latency | 10k samples + 1M spike | Runtime < 2.5s, monotonic | Elapsed: 0.72s, P50 CI: (7.115, 7.642) | **PASS** |
| ST-10 | Ablation 5-Dim | Immutability of sc | Baseline unchanged | All original fields untouched | **PASS** |
| ST-11 | Ablation Artifacts | Run all 5 dimensions | 5 JSON artifacts | All 5 files emitted and valid | **PASS** |

The regression and stress suite is permanently archived in `evals/capri_comprehensive/tests/test_stress_m2.py`.

---

## 5. Caveats

1. The critical defect in `_normal_ppf` does not affect nominal 95% Wilson confidence intervals because $p=0.975$ falls inside the central polynomial regime. It only activates for confidence levels $\ge 95.15\%$.
2. In accordance with the Review-Only constraint, Challenger did not modify `metrics.py` or `ablation_runner.py` directly; modifications must be performed by the Worker.

---

## 6. Conclusion & Verdict

**Verdict: REQUEST_CHANGES**

Milestone M2 is fundamentally well-engineered, but cannot be approved until the following two items are addressed by Worker:
1. **Fix `_normal_ppf` in `metrics.py:78-81`** to correctly return `x` for $p < p_{low}$ and `-x` for $p > p_{high}$, resolving the sign inversion bug and ensuring valid Wilson intervals for all confidence levels.
2. **Fix `p50_latency_ms` calculation in `ablation_runner.py:119,132`** to use `np.percentile(rep.latencies_ms, 50)` instead of `rep.latencies_ms[0]`.

Once Worker applies these targeted fixes, `test_stress_m2.py` should be updated to make `test_wilson_score_high_confidence_99_bug_reproduction` a standard passing assertion, achieving full mathematical integrity for Milestone M2.

---

## 7. Verification Method

To independently reproduce all empirical findings:

```bash
# 1. Run the empirical stress test suite (verifies 12 PASS, 1 XFAIL for bug reproduction)
uv run pytest evals/capri_comprehensive/tests/test_stress_m2.py -v

# 2. Directly observe the inverted Wilson bounds at 99% confidence
uv run python -c "
from evals.capri_comprehensive.statistical_analysis.metrics import wilson_score_interval
low, high = wilson_score_interval(90, 100, confidence=0.99)
print(f'99% CI for 90/100: low={low}, high={high}')
assert low <= high, 'CRITICAL: low > high!'
"

# 3. Directly observe the negative quantile in _normal_ppf tail
uv run python -c "
from evals.capri_comprehensive.statistical_analysis.metrics import _normal_ppf
print('p=0.995 z-score:', _normal_ppf(0.995), '(Expected: +2.5758)')
"
```
