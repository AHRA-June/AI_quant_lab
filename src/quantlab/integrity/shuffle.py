"""Shuffle control (F7.4).

A strategy must beat a null in which its signal carries no cross-sectional
information. We destroy that information by permuting the signal *across names
within each date* (preserving the per-date distribution and the market/factor
exposure), recompute the performance metric many times to build a null
distribution, and report the empirical p-value.

A single shuffle is too noisy to gate on; the default is 100 shuffles, and the
decision rule is ``p < 0.05`` (PRD §F7.4), not "beat one shuffle".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

MetricFn = Callable[[pd.DataFrame], float]


@dataclass
class ShuffleResult:
    observed: float
    p_value: float
    null_mean: float
    null_std: float
    n_shuffles: int

    @property
    def survives(self) -> bool:
        """True iff the strategy beats the shuffle null at p < 0.05."""
        return self.p_value < 0.05


def _shuffle_rows(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Permute non-NaN values within each row independently."""
    out = df.to_numpy(copy=True)
    for i in range(out.shape[0]):
        row = out[i]
        mask = ~np.isnan(row)
        vals = row[mask]
        rng.shuffle(vals)
        row[mask] = vals
    return pd.DataFrame(out, index=df.index, columns=df.columns)


def shuffle_pvalue(
    signal: pd.DataFrame,
    metric_fn: MetricFn,
    *,
    n_shuffles: int = 100,
    seed: int = 0,
    higher_is_better: bool = True,
) -> ShuffleResult:
    """Empirical p-value of ``metric_fn(signal)`` against a shuffled null.

    ``metric_fn`` maps a signal panel to a scalar score (e.g. mean rank IC, or a
    backtest Sharpe via a closure). Larger is better unless
    ``higher_is_better=False``.
    """
    rng = np.random.default_rng(seed)
    observed = metric_fn(signal)
    null = np.array([metric_fn(_shuffle_rows(signal, rng)) for _ in range(n_shuffles)])

    if higher_is_better:
        exceed = int((null >= observed).sum())
    else:
        exceed = int((null <= observed).sum())
    p_value = (exceed + 1) / (n_shuffles + 1)  # +1 smoothing (never exactly 0)

    return ShuffleResult(
        observed=float(observed),
        p_value=float(p_value),
        null_mean=float(np.mean(null)),
        null_std=float(np.std(null)),
        n_shuffles=n_shuffles,
    )
