"""Turn an alpha signal panel into long-only target weights.

The backtest engine consumes a target-weight matrix (F4.1). This module is the
bridge: alpha (dates × tickers) → weights (dates × tickers), selecting the
top-``n`` names per rebalance date. Only names present in that date's universe
(non-NaN alpha) are eligible, which keeps selection point-in-time.
"""

from __future__ import annotations

import pandas as pd

# Period aliases for ``DatetimeIndex.to_period`` (note: "M", not the resample
# alias "ME" — to_period rejects the latter).
_REBALANCE_FREQ = {"daily": None, "weekly": "W", "monthly": "M"}


def apply_rebalance(weights: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Keep target weights only on rebalance dates; NaN elsewhere.

    The engine forward-fills between rebalances, so blanking non-rebalance rows
    means "hold" rather than "go to cash". Rebalance dates are the last trading
    day within each period (weekly/monthly); ``daily`` is a no-op.
    """
    if freq not in _REBALANCE_FREQ:
        raise ValueError(f"unknown rebalance freq: {freq}")
    rule = _REBALANCE_FREQ[freq]
    if rule is None:
        return weights
    # last available trading day within each calendar period
    reb_dates = weights.index.to_series().groupby(weights.index.to_period(rule)).max()
    masked = weights.copy()
    masked.loc[~weights.index.isin(reb_dates.values)] = float("nan")
    return masked


def top_n_long_only(
    alpha: pd.DataFrame,
    n_positions: int,
    *,
    weighting: str = "equal",
) -> pd.DataFrame:
    """Select the top-``n_positions`` by alpha each date and weight them.

    Parameters
    ----------
    alpha : dates × tickers panel. NaN = not in universe / no signal that date.
    n_positions : number of names to hold.
    weighting : ``"equal"`` (1/n each) or ``"proportional"`` (∝ rank within
        the selected set; always non-negative, long-only).

    Returns a weight matrix (rows sum to 1 on dates with ≥1 pick, else 0).
    """
    if weighting not in ("equal", "proportional"):
        raise ValueError(f"unknown weighting: {weighting}")

    weights = pd.DataFrame(0.0, index=alpha.index, columns=alpha.columns)
    for dt, row in alpha.iterrows():
        valid = row.dropna()
        if valid.empty:
            continue
        picks = valid.nlargest(min(n_positions, len(valid)))
        if weighting == "equal":
            w = pd.Series(1.0 / len(picks), index=picks.index)
        else:  # proportional to rank among the picks (min rank -> smallest weight)
            r = picks.rank()
            w = r / r.sum()
        weights.loc[dt, w.index] = w.values
    return weights
