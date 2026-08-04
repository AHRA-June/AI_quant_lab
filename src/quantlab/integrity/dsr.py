"""Deflated Sharpe Ratio and effective number of trials (F7.2).

Reference: Bailey & López de Prado (2014), "The Deflated Sharpe Ratio".

The core idea: after selecting the best of ``N`` trials, a high Sharpe is
partly luck. DSR is the probability that the *true* Sharpe exceeds zero, after
deflating for the number of trials, the variance of Sharpes across trials, the
sample length, and the returns' skew/kurtosis.

Crucial refinement (PRD §DSR): the trial count that matters is the **effective**
number of *independent* trials, not the raw count — 200 near-duplicate alpha
variants are not 200 independent bets. :func:`effective_num_trials` collapses
correlated trials into clusters and counts those.
"""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

_N01 = NormalDist()
_EULER = 0.5772156649015329


def expected_max_sharpe(var_sharpe: float, n_trials: int) -> float:
    """Expected maximum of ``n_trials`` Sharpe estimates under the null (SR0).

    ``var_sharpe`` is the variance of the Sharpe estimates *across trials*.
    """
    if n_trials < 1:
        raise ValueError("n_trials must be >= 1")
    if n_trials == 1:
        return 0.0
    sigma = np.sqrt(var_sharpe)
    a = _N01.inv_cdf(1 - 1.0 / n_trials)
    b = _N01.inv_cdf(1 - 1.0 / (n_trials * np.e))
    return float(sigma * ((1 - _EULER) * a + _EULER * b))


def deflated_sharpe_ratio(
    sharpe: float,
    *,
    n_trials: int,
    var_sharpe: float,
    n_obs: int,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Probability the true Sharpe > 0 after deflation (in ``[0, 1]``).

    All Sharpe inputs are **per-observation** (non-annualized). ``kurtosis`` is
    non-excess (normal = 3). A DSR near 1 means the result survives the
    multiple-testing haircut; near 0.5 or below means it's indistinguishable
    from luck.
    """
    sr0 = expected_max_sharpe(var_sharpe, n_trials)
    denom = 1.0 - skew * sharpe + (kurtosis - 1.0) / 4.0 * sharpe**2
    if denom <= 0 or n_obs <= 1:
        return float("nan")
    z = (sharpe - sr0) * np.sqrt(n_obs - 1) / np.sqrt(denom)
    return float(_N01.cdf(z))


def effective_num_trials(returns_by_trial: pd.DataFrame, corr_threshold: float = 0.7) -> int:
    """Effective number of *independent* trials via correlation clustering.

    ``returns_by_trial`` has one column per trial (its return/signal series).
    Trials whose absolute correlation ≥ ``corr_threshold`` are merged
    (union-find over the correlation graph); the number of connected components
    is the effective trial count. Dependency-free by design.
    """
    cols = list(returns_by_trial.columns)
    n = len(cols)
    if n <= 1:
        return n
    corr = returns_by_trial.corr().abs().to_numpy()

    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        parent[find(i)] = find(j)

    for i in range(n):
        for j in range(i + 1, n):
            if corr[i, j] >= corr_threshold:
                union(i, j)

    return len({find(i) for i in range(n)})
