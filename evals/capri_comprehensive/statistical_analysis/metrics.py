"""Statistical metrics and confidence interval computation for Capri evaluation.

Implements:
1. Wilson score confidence interval for binomial success rates.
2. Non-parametric bootstrap confidence intervals for latency percentiles (P50, P90, P95).
3. Summary statistical aggregators avoiding misleading single-point estimates.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np


def _normal_ppf(p: float) -> float:
    """Accurate inverse of the standard normal cumulative distribution function (Quantile function).

    Uses the Beasley-Springer-Moro rational approximation algorithm (Wichura / Abramowitz & Stegun).
    Accurate to within 1e-9 across the full probability domain (0, 1).
    """
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"Probability p must be in (0, 1), got {p}")

    # Coefficients for approximation
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]

    p_low = 0.02425
    p_high = 1.0 - p_low

    if p_low <= p <= p_high:
        q = p - 0.5
        r = q * q
        numerator = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
        denominator = ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0
        return numerator / denominator

    # Tail regions
    if p < p_low:
        r = math.sqrt(-2.0 * math.log(p))
    else:
        r = math.sqrt(-2.0 * math.log(1.0 - p))

    numerator = ((((c[0] * r + c[1]) * r + c[2]) * r + c[3]) * r + c[4]) * r + c[5]
    denominator = (((d[0] * r + d[1]) * r + d[2]) * r + d[3]) * r + 1.0
    x = numerator / denominator

    if p < p_low:
        return x
    return -x


def wilson_score_interval(
    successes: int,
    total: int,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Calculate the Wilson score confidence interval for a binomial proportion.

    Unlike the Wald (normal approximation) interval, the Wilson score interval:
    - Never produces bounds outside [0, 1].
    - Works accurately for extreme proportions (p=0 or p=1) and small sample sizes.
    - Avoids zero-width intervals when successes == 0 or successes == total.

    Args:
        successes: Number of successful outcomes (k).
        total: Total number of trials (n).
        confidence: Confidence level (default: 0.95 for 95% CI).

    Returns:
        tuple[float, float]: (lower_bound, upper_bound) rounded to 6 decimal places.
    """
    if total <= 0:
        return 0.0, 0.0
    if successes < 0 or successes > total:
        raise ValueError(f"Successes ({successes}) must be between 0 and total ({total})")
    if not (0.0 < confidence < 1.0):
        raise ValueError(f"Confidence must be between 0 and 1, got {confidence}")

    alpha = 1.0 - confidence
    z = _normal_ppf(1.0 - alpha / 2.0)
    z_sq = z * z

    n = float(total)
    p = float(successes) / n

    denominator = 1.0 + z_sq / n
    center = (p + z_sq / (2.0 * n)) / denominator
    margin = (z * math.sqrt((p * (1.0 - p) / n) + (z_sq / (4.0 * n * n)))) / denominator

    low = max(0.0, center - margin)
    high = min(1.0, center + margin)

    return round(low, 6), round(high, 6)


def bootstrap_ci(
    data: Sequence[float],
    stat_func: Callable[[np.ndarray], float],
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Calculate non-parametric bootstrap confidence interval for an arbitrary statistic.

    Args:
        data: Sequence of numerical values.
        stat_func: Function accepting a 1D numpy array and returning a float.
        n_bootstrap: Number of bootstrap resamples (default: 1000).
        confidence: Confidence level (default: 0.95 for 95% CI).
        seed: Random seed for reproducibility.

    Returns:
        tuple[float, float]: (lower_bound, upper_bound)
    """
    if len(data) == 0:
        return 0.0, 0.0
    arr = np.asarray(data, dtype=np.float64)
    n = len(arr)
    if n == 1:
        val = float(stat_func(arr))
        return val, val

    rng = np.random.RandomState(seed)
    bootstrap_samples = rng.choice(arr, size=(n_bootstrap, n), replace=True)
    bootstrap_stats = np.apply_along_axis(stat_func, 1, bootstrap_samples)

    alpha = 1.0 - confidence
    low_pct = (alpha / 2.0) * 100.0
    high_pct = (1.0 - alpha / 2.0) * 100.0

    low = float(np.percentile(bootstrap_stats, low_pct))
    high = float(np.percentile(bootstrap_stats, high_pct))
    return round(low, 3), round(high, 3)


def bootstrap_percentile_ci(
    data: Sequence[float],
    percentile: float,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> tuple[float, float]:
    """Calculate non-parametric bootstrap confidence interval for a specific percentile."""

    def p_func(sample: np.ndarray) -> float:
        return float(np.percentile(sample, percentile))

    return bootstrap_ci(
        data=data,
        stat_func=p_func,
        n_bootstrap=n_bootstrap,
        confidence=confidence,
        seed=seed,
    )


def calculate_latency_summary(
    latencies_ms: Sequence[float],
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 42,
) -> dict[str, Any]:
    """Compute exhaustive latency metrics with P50, P90, P95 bootstrap confidence intervals.

    Args:
        latencies_ms: Sequence of latency measurements in milliseconds.
        n_bootstrap: Resampling trials (default: 1000).
        confidence: Confidence level (default: 0.95).
        seed: Random seed for bootstrap reproducibility.

    Returns:
        Dictionary with count, mean, std, min, P50, P90, P95, P99, max and bootstrap CIs.
    """
    if len(latencies_ms) == 0:
        return {
            "count": 0,
            "mean": 0.0,
            "std": 0.0,
            "min": 0.0,
            "p50": 0.0,
            "p50_ci": (0.0, 0.0),
            "p90": 0.0,
            "p90_ci": (0.0, 0.0),
            "p95": 0.0,
            "p95_ci": (0.0, 0.0),
            "p99": 0.0,
            "max": 0.0,
        }

    arr = np.asarray(latencies_ms, dtype=np.float64)
    p50 = float(np.percentile(arr, 50))
    p90 = float(np.percentile(arr, 90))
    p95 = float(np.percentile(arr, 95))
    p99 = float(np.percentile(arr, 99))

    p50_ci = bootstrap_percentile_ci(
        arr, 50, n_bootstrap=n_bootstrap, confidence=confidence, seed=seed
    )
    p90_ci = bootstrap_percentile_ci(
        arr, 90, n_bootstrap=n_bootstrap, confidence=confidence, seed=seed + 1
    )
    p95_ci = bootstrap_percentile_ci(
        arr, 95, n_bootstrap=n_bootstrap, confidence=confidence, seed=seed + 2
    )

    return {
        "count": len(arr),
        "mean": round(float(np.mean(arr)), 3),
        "std": round(float(np.std(arr, ddof=1 if len(arr) > 1 else 0)), 3),
        "min": round(float(np.min(arr)), 3),
        "p50": round(p50, 3),
        "p50_ci": p50_ci,
        "p90": round(p90, 3),
        "p90_ci": p90_ci,
        "p95": round(p95, 3),
        "p95_ci": p95_ci,
        "p99": round(p99, 3),
        "max": round(float(np.max(arr)), 3),
    }


def calculate_binomial_summary(
    successes: int,
    total: int,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Compute binomial pass rate and Wilson score confidence interval."""
    if total <= 0:
        return {
            "successes": 0,
            "total": 0,
            "raw_rate": 0.0,
            "ci_low": 0.0,
            "ci_high": 0.0,
            "confidence": confidence,
            "formatted": "N/A (0/0)",
        }

    rate = successes / total
    ci_low, ci_high = wilson_score_interval(successes, total, confidence=confidence)
    formatted = f"{rate * 100:.1f}% [{ci_low * 100:.1f}%, {ci_high * 100:.1f}%]"

    return {
        "successes": successes,
        "total": total,
        "raw_rate": round(rate, 4),
        "ci_low": ci_low,
        "ci_high": ci_high,
        "confidence": confidence,
        "formatted": formatted,
    }
