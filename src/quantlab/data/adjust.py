"""Price adjustment (DQ.1).

Principle: **store raw OHLCV + an adjustment-factor series, apply at read
time.** We never persist a pre-adjusted snapshot, because a later corporate
action (split, rights issue) would silently re-adjust an already-adjusted
series and corrupt history. Raw prices are immutable; only the factor changes.

Factor definition
-----------------
``factor[t] = adjusted_close[t] / raw_close[t]``

To reconstruct an adjusted panel at read time:
    adjusted OHLC  = raw OHLC * factor      (prices scale down going back in time)
    adjusted volume = raw volume / factor    (share count scales up)

``value`` (거래대금, price*volume) is invariant under a pure split adjustment,
so it is left unchanged.
"""

from __future__ import annotations

import pandas as pd

from quantlab.types import OHLCV_COLUMNS

_PRICE_COLS = ("open", "high", "low", "close")


def derive_factor(raw_close: pd.Series, adjusted_close: pd.Series) -> pd.Series:
    """Compute the adjustment factor from raw and adjusted close series.

    The two series are aligned on their common index; any date missing from
    either side is dropped. Result is named ``factor``.
    """
    raw, adj = raw_close.align(adjusted_close, join="inner")
    factor = (adj / raw).rename("factor")
    return factor


def apply_adjustment(raw_ohlcv: pd.DataFrame, factor: pd.Series) -> pd.DataFrame:
    """Return an adjusted copy of ``raw_ohlcv`` using ``factor``.

    Missing factor values are treated as 1.0 (no adjustment) rather than
    propagating NaN, so a partial factor series never blanks out prices.
    """
    missing = [c for c in OHLCV_COLUMNS if c not in raw_ohlcv.columns]
    if missing:
        raise ValueError(f"raw_ohlcv missing columns: {missing}")

    f = factor.reindex(raw_ohlcv.index).fillna(1.0)
    out = raw_ohlcv.copy()
    for col in _PRICE_COLS:
        out[col] = raw_ohlcv[col] * f
    out["volume"] = raw_ohlcv["volume"] / f
    # 'value' (turnover) is adjustment-invariant; leave as-is.
    return out
