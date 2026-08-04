"""Prediction targets (F3.1) — cross-sectional rank of forward returns.

The target is the rank of each name's ``horizon``-day forward return within its
date's cross-section, normalized to ``[-0.5, 0.5]``. Predicting relative rank
(not absolute return, not up/down direction) is what a long-only top-N strategy
actually needs, and it strips out the market-beta component that dominates a
binary up/down label (PRD §질문3).

``forward_return`` deliberately looks FORWARD — it is a label, never a feature.
The walk-forward split's embargo (F3.4) keeps that future peek out of training.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def forward_return(close: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """``horizon``-day forward simple return: close(t+h)/close(t) - 1."""
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    return close.shift(-horizon) / close - 1.0


def rank_label(fwd: pd.DataFrame) -> pd.DataFrame:
    """Cross-sectional rank per date, mapped to ``[-0.5, 0.5]`` (min→-0.5,
    max→+0.5), which is exactly zero-mean per date. Single-name dates → NaN."""
    r = fwd.rank(axis=1)
    cnt = fwd.notna().sum(axis=1)
    denom = (cnt - 1).replace(0, np.nan)
    return r.sub(1).div(denom, axis=0) - 0.5
