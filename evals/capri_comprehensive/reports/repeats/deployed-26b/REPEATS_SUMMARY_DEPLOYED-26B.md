# Repeated runs — deployed-26b

- Runs: 3; runnable scenarios per run: 80
- Passed per run: 45, 43, 47 (mean 45.0, SD 2.0)
- Pooled pass rate: 135/240 = 56.2% (Wilson 95% CI 49.9–62.4%; runs are not independent samples of scenarios, so this interval understates scenario-level uncertainty)
- Stable pass (3/3): 41; stable fail (0/3): 30; flaky: 9

## Flaky scenarios

| Scenario | Passed |
|:---|---:|
| AUT-02 | 1/3 |
| AUT-06 | 2/3 |
| INT-03 | 2/3 |
| INT-04 | 1/3 |
| JOURNEY-02 | 1/3 |
| LT-04 | 2/3 |
| LT-05 | 1/3 |
| MEM-10 | 1/3 |
| SEC-12 | 1/3 |

## Stable fail (0/3)

AUT-07, CM-01, CM-06, INT-01, INT-06, INT-07, INT-08, JOURNEY-01, JOURNEY-03, JOURNEY-04, LT-02, LT-03, LT-06, LT-08, MEM-01, MEM-03, MEM-04, MEM-07, RE-05, RE-07, REL-08, SEC-04, SEC-05, SEC-06, SEC-07, SEC-08, SEC-09, SEC-11, VOI-01, VOI-02
