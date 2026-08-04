"""Seven hand-crafted cross-sectional factor strategies.

Each returns an ``alpha`` panel (dates × tickers); higher = more attractive to
hold long. Built purely from primitives so they double as the empirical basis
for the M2 DSL operator set. Classic factors adapted to KRX daily data.
"""

from __future__ import annotations

import pandas as pd

from quantlab.factors import primitives as P


def momentum_12_1(close: pd.DataFrame) -> pd.DataFrame:
    """12-1 momentum: ~250d return skipping the most recent 20d (reversal gap)."""
    long_ret = P.returns(P.delay(close, 20), 230)
    return P.rank(long_ret)


def short_term_reversal(close: pd.DataFrame) -> pd.DataFrame:
    """Short-term reversal: buy recent losers (−5d return)."""
    return P.rank(-P.returns(close, 5))


def volume_breakout(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """Volume surge: short-window vs long-window average volume."""
    surge = P.ts_mean(volume, 5) / P.ts_mean(volume, 20)
    return P.rank(surge)


def low_volatility(close: pd.DataFrame) -> pd.DataFrame:
    """Low-volatility anomaly: prefer low 20d return volatility."""
    vol = P.ts_std(P.returns(close, 1), 20)
    return P.rank(-vol)


def momentum_volume_combo(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """20d momentum confirmed by volume expansion (product of two ranks)."""
    mom = P.rank(P.returns(close, 20))
    vol = P.rank(P.ts_mean(volume, 5) / P.ts_mean(volume, 20))
    return mom * vol


def near_52w_high(close: pd.DataFrame) -> pd.DataFrame:
    """Proximity to the trailing 250d high (52-week-high effect)."""
    proximity = close / P.ts_max(close, 250)
    return P.rank(proximity)


def zscore_reversion(close: pd.DataFrame) -> pd.DataFrame:
    """Mean reversion on the 20d rolling z-score of price (buy the dips)."""
    return P.rank(-P.ts_zscore(close, 20))


# Registry: name -> (fn, needs_volume)
STRATEGIES = {
    "momentum_12_1": (momentum_12_1, False),
    "short_term_reversal": (short_term_reversal, False),
    "volume_breakout": (volume_breakout, True),
    "low_volatility": (low_volatility, False),
    "momentum_volume_combo": (momentum_volume_combo, True),
    "near_52w_high": (near_52w_high, False),
    "zscore_reversion": (zscore_reversion, False),
}
