# Repeated runs — deployed-31b

- Runs: 3; runnable scenarios per run: 80
- Passed per run: 45, 45, 42 (mean 44.0, SD 1.7)
- Pooled pass rate: 132/240 = 55.0% (Wilson 95% CI 48.7–61.2%; runs are not independent samples of scenarios, so this interval understates scenario-level uncertainty)
- Stable pass (3/3): 41; stable fail (0/3): 33; flaky: 6
- Scenario verdicts that differ between pairs of runs: run1–run2: 4, run1–run3: 5, run2–run3: 3 (the totals hide flips in both directions)

## Flaky scenarios

| Scenario | Passed |
|:---|---:|
| AUT-01 | 2/3 |
| JOURNEY-02 | 1/3 |
| LT-03 | 1/3 |
| LT-04 | 2/3 |
| RE-05 | 2/3 |
| SEC-12 | 1/3 |

## Stable fail (0/3)

AUT-02, AUT-06, AUT-07, CM-01, CM-06, INT-01, INT-04, INT-06, INT-07, INT-08, JOURNEY-01, JOURNEY-03, JOURNEY-04, LT-02, LT-06, LT-08, MEM-01, MEM-02, MEM-03, MEM-04, MEM-05, MEM-07, RE-07, REL-08, SEC-03, SEC-04, SEC-05, SEC-06, SEC-07, SEC-08, SEC-09, SEC-11, VOI-02
