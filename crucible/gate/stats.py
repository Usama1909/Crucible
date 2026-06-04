"""
Crucible Gate — Statistics
Bailey & Lopez de Prado Deflated Sharpe Ratio.
Corrected: benchmark scales by sqrt(1/n_obs).
"""
import math
import numpy as np
from scipy.stats import norm
from typing import List

EULER = 0.5772156649015329

def sharpe_ratio(returns) -> float:
    r = np.asarray(returns, dtype=float)
    if len(r) < 2:
        return 0.0
    sd = r.std(ddof=1)
    return 0.0 if sd == 0 else float(r.mean() / sd)

def expected_max_sharpe(n_candidates: int, n_obs: int) -> float:
    """Expected Sharpe of best luck-only candidate from n_candidates trials."""
    if n_candidates < 2 or n_obs < 2:
        return 0.0
    sigma_sr = math.sqrt(1.0 / n_obs)
    a = norm.ppf(1.0 - 1.0 / n_candidates)
    b = norm.ppf(1.0 - 1.0 / (n_candidates * math.e))
    return sigma_sr * ((1.0 - EULER) * a + EULER * b)

def deflated_sharpe_ratio(sharpe: float, n_candidates: int, n_obs: int) -> float:
    """P(edge beats luck benchmark). DSR < 0.95 = not proven."""
    if n_obs < 2:
        return 0.0
    sr0 = expected_max_sharpe(n_candidates, n_obs)
    z = (sharpe - sr0) * math.sqrt(n_obs - 1)
    return float(norm.cdf(z))

def t_test_mean(returns: List[float]) -> tuple:
    """One-sample t-test: is mean > 0? Returns (mean, p_value)."""
    from scipy import stats as scipy_stats
    arr = np.array(returns)
    if len(arr) < 2:
        return 0.0, 1.0
    result = scipy_stats.ttest_1samp(arr, 0.0, alternative='greater')
    return float(np.mean(arr)), float(result.pvalue)

def stability_score(returns: List[float], n_splits: int = 3,
                    min_positive: int = 2) -> bool:
    """True if at least min_positive of n_splits have positive mean."""
    arr = np.array(returns)
    if len(arr) < n_splits:
        return False
    splits = np.array_split(arr, n_splits)
    positive = sum(1 for s in splits if np.mean(s) > 0)
    return positive >= min_positive