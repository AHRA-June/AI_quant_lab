"""Point-in-time factor operators.

Convention: a *panel* is a ``DataFrame`` indexed by date (rows, ascending) with
one column per ticker. Time-series operators act down ``axis=0`` using only
trailing data; cross-sectional operators act across ``axis=1`` within a single
row (date), so a value at date ``t`` never depends on any date ``> t``.

The suite mirrors the WorldQuant Alpha-expression lineage but every operator is
audited for look-ahead (see ``tests/test_primitives.py::test_no_lookahead``).
"""

from __future__ import annotations

import pandas as pd

Panel = pd.DataFrame

# --- time-series (backward-only) ------------------------------------------


def delay(x: Panel, n: int = 1) -> Panel:
    """Value ``n`` periods ago (``n > 0`` looks back)."""
    if n < 0:
        raise ValueError("delay(n) must not look forward (n >= 0)")
    return x.shift(n)


def delta(x: Panel, n: int = 1) -> Panel:
    """Change vs. ``n`` periods ago: ``x_t - x_{t-n}``."""
    return x - x.shift(n)


def returns(x: Panel, n: int = 1) -> Panel:
    """Simple return over ``n`` periods: ``x_t / x_{t-n} - 1``."""
    return x / x.shift(n) - 1.0


def ts_sum(x: Panel, n: int) -> Panel:
    return x.rolling(n).sum()


def ts_mean(x: Panel, n: int) -> Panel:
    return x.rolling(n).mean()


def ts_std(x: Panel, n: int) -> Panel:
    return x.rolling(n).std()


def ts_min(x: Panel, n: int) -> Panel:
    return x.rolling(n).min()


def ts_max(x: Panel, n: int) -> Panel:
    return x.rolling(n).max()


def ts_rank(x: Panel, n: int) -> Panel:
    """Trailing percentile rank of the current value within its ``n``-window."""
    return x.rolling(n).rank(pct=True)


def ts_zscore(x: Panel, n: int) -> Panel:
    """Rolling z-score using trailing mean/std (backward-only)."""
    m = x.rolling(n).mean()
    s = x.rolling(n).std()
    return (x - m) / s


# --- cross-sectional (single date, no time dependency) --------------------


def rank(x: Panel) -> Panel:
    """Cross-sectional percentile rank per date, in ``[0, 1]``."""
    return x.rank(axis=1, pct=True)


def cs_demean(x: Panel) -> Panel:
    """Subtract the cross-sectional mean per date."""
    return x.sub(x.mean(axis=1), axis=0)


def cs_zscore(x: Panel) -> Panel:
    """Cross-sectional z-score per date."""
    return x.sub(x.mean(axis=1), axis=0).div(x.std(axis=1), axis=0)


def scale(x: Panel, a: float = 1.0) -> Panel:
    """Scale each date's row so the sum of absolute values equals ``a``."""
    denom = x.abs().sum(axis=1)
    return x.div(denom, axis=0) * a


# Registry consumed by the M2 whitelist parser (names it is allowed to bind).
OPERATORS = {
    fn.__name__: fn
    for fn in (
        delay,
        delta,
        returns,
        ts_sum,
        ts_mean,
        ts_std,
        ts_min,
        ts_max,
        ts_rank,
        ts_zscore,
        rank,
        cs_demean,
        cs_zscore,
        scale,
    )
}
