"""Feature construction (F3.3) — built ONLY from leak-proof primitives.

Every feature is a backward-looking panel, then cross-sectionally z-scored per
date (a single-date op — no time leakage). Using the same
:mod:`quantlab.factors.primitives` as the DSL means features and alphas share
one audited, look-ahead-free vocabulary.
"""

from __future__ import annotations

import pandas as pd

from quantlab.factors import primitives as P


def _mom(close: pd.DataFrame, n: int) -> pd.DataFrame:
    return P.returns(close, n)


def _reversal(close: pd.DataFrame, n: int) -> pd.DataFrame:
    return -P.returns(close, n)


def _low_vol(close: pd.DataFrame, n: int) -> pd.DataFrame:
    return -P.ts_std(P.returns(close, 1), n)


def _volume_surge(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    return P.ts_mean(volume, 5) / P.ts_mean(volume, 20)


def _near_high(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    return close / P.ts_max(close, 250)


# name -> (fn, needs_volume). fn(close) or fn(close, volume).
FEATURES = {
    "mom_20": (lambda c: _mom(c, 20), False),
    "mom_60": (lambda c: _mom(c, 60), False),
    "rev_5": (lambda c: _reversal(c, 5), False),
    "low_vol_20": (lambda c: _low_vol(c, 20), False),
    "vol_surge": (_volume_surge, True),
    "near_high": (_near_high, True),
}


def build_features(close: pd.DataFrame, volume: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Return {name: cross-sectionally z-scored feature panel}.

    Cross-sectional z-scoring (per date) puts every feature on the same scale
    for the model without touching the time axis — no look-ahead.
    """
    out: dict[str, pd.DataFrame] = {}
    for name, (fn, needs_vol) in FEATURES.items():
        raw = fn(close, volume) if needs_vol else fn(close)
        out[name] = P.cs_zscore(raw)
    return out
