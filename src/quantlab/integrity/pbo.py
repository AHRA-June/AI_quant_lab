"""Probability of Backtest Overfitting (F7.3).

Reference: Bailey, Borwein, López de Prado & Zhu (2017), "The Probability of
Backtest Overfitting" — Combinatorially Symmetric Cross-Validation (CSCV).

Given a matrix of per-period performance for *many* candidate strategies, CSCV
asks: when you pick the in-sample best, how often does it land in the *worse*
half out-of-sample? A high PBO means your selection procedure is overfitting —
the IS winner is essentially random OOS. This complements the Deflated Sharpe
Ratio: DSR asks "is this one Sharpe real?", PBO asks "is my whole
select-the-best process trustworthy?".
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd


@dataclass
class PBOResult:
    pbo: float                 # probability of backtest overfitting, in [0, 1]
    logits: np.ndarray         # per-combination logit λ; PBO = P(λ <= 0)
    n_combinations: int

    @property
    def overfit(self) -> bool:
        """Rule of thumb: PBO > 0.5 means the selection is worse than a coin flip."""
        return self.pbo > 0.5


def _sharpe(block: np.ndarray) -> np.ndarray:
    """Per-column Sharpe of a (rows x strategies) block; 0 where std is 0."""
    mean = block.mean(axis=0)
    std = block.std(axis=0)
    out = np.zeros_like(mean)
    nz = std > 0
    out[nz] = mean[nz] / std[nz]
    return out


def probability_of_backtest_overfitting(
    performance: pd.DataFrame, *, n_blocks: int = 8
) -> PBOResult:
    """CSCV PBO over a (time x strategy) performance matrix.

    ``performance`` columns are candidate strategies, rows are per-period
    returns. Rows are split into ``n_blocks`` (even) contiguous blocks; every
    balanced split into in-sample / out-of-sample halves contributes one trial.
    """
    if n_blocks % 2 != 0:
        raise ValueError("n_blocks must be even")
    M = performance.dropna(how="any").to_numpy(dtype=float)
    n_strategies = M.shape[1]
    if n_strategies < 2:
        raise ValueError("need >= 2 strategies to assess overfitting")

    blocks = np.array_split(np.arange(M.shape[0]), n_blocks)
    all_idx = set(range(n_blocks))

    logits: list[float] = []
    for is_blocks in combinations(range(n_blocks), n_blocks // 2):
        oos_blocks = sorted(all_idx - set(is_blocks))
        is_rows = np.concatenate([blocks[b] for b in is_blocks])
        oos_rows = np.concatenate([blocks[b] for b in oos_blocks])

        is_perf = _sharpe(M[is_rows])
        oos_perf = _sharpe(M[oos_rows])

        best = int(np.argmax(is_perf))
        # relative rank of the IS-best among OOS performances, in (0, 1)
        rank = float((oos_perf <= oos_perf[best]).sum())
        omega = rank / (n_strategies + 1)
        omega = min(max(omega, 1e-6), 1 - 1e-6)
        logits.append(np.log(omega / (1 - omega)))

    arr = np.array(logits)
    pbo = float((arr <= 0).mean())
    return PBOResult(pbo=pbo, logits=arr, n_combinations=len(arr))
