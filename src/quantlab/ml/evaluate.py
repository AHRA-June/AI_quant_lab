"""ML evaluation (F3.5) — Rank IC / IC IR / quantile spread.

Rank IC and IC IR come from :mod:`quantlab.backtest.metrics` (shared with the
backtest layer). Quantile spread — top minus bottom quantile forward return —
is the economically meaningful complement: it says whether the top-ranked names
actually out-return the bottom-ranked ones.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantlab.backtest.metrics import ic_ir, rank_ic


def quantile_spread(
    prediction: pd.DataFrame, forward_returns: pd.DataFrame, q: int = 5
) -> float:
    """Mean per-date (top-quantile − bottom-quantile) forward return."""
    spreads = []
    fwd = forward_returns.reindex(index=prediction.index, columns=prediction.columns)
    for dt, row in prediction.iterrows():
        r = fwd.loc[dt]
        mask = row.notna() & r.notna()
        if mask.sum() < q:
            continue
        pr, rr = row[mask], r[mask]
        ranks = pr.rank(method="first")
        bins = pd.qcut(ranks, q, labels=False, duplicates="drop")
        top, bot = rr[bins == bins.max()], rr[bins == bins.min()]
        if len(top) and len(bot):
            spreads.append(top.mean() - bot.mean())
    return float(np.mean(spreads)) if spreads else float("nan")


def evaluate_predictions(
    prediction: pd.DataFrame, forward_returns: pd.DataFrame, q: int = 5
) -> dict:
    """Bundle the standard M3 evaluation metrics."""
    daily_ic = rank_ic(prediction, forward_returns)
    return {
        "rank_ic_mean": float(daily_ic.mean()),
        "ic_ir": ic_ir(daily_ic),
        "quantile_spread": quantile_spread(prediction, forward_returns, q=q),
        "n_days": int(len(daily_ic)),
    }
