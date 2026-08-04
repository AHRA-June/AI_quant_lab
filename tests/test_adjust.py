"""DQ.1 raw + factor adjustment."""

import numpy as np
import pandas as pd

from quantlab.data.adjust import apply_adjustment, derive_factor


def _frame(closes):
    idx = pd.bdate_range("2024-01-01", periods=len(closes))
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame(
        {"open": c, "high": c, "low": c, "close": c, "volume": 1000.0, "value": c * 1000.0}
    )


def test_factor_is_one_when_no_corporate_action():
    raw = _frame([100, 101, 102, 103])
    factor = derive_factor(raw["close"], raw["close"])
    assert np.allclose(factor.values, 1.0)


def test_split_factor_and_read_time_adjustment():
    # 2:1 split after index 2: raw closes drop by half; adjusted back-halves the pre-split part.
    raw = _frame([100, 100, 50, 50])
    adj_close = pd.Series([50, 50, 50, 50], index=raw.index, dtype=float)
    factor = derive_factor(raw["close"], adj_close)
    assert np.allclose(factor.values, [0.5, 0.5, 1.0, 1.0])

    adjusted = apply_adjustment(raw, factor)
    # Prices scale by factor; volume scales inversely; adjusted close is continuous.
    assert np.allclose(adjusted["close"].values, [50, 50, 50, 50])
    assert np.allclose(adjusted["volume"].values, [2000, 2000, 1000, 1000])
    # turnover (value) is adjustment-invariant.
    assert np.allclose(adjusted["value"].values, raw["value"].values)


def test_missing_factor_defaults_to_no_adjustment():
    raw = _frame([100, 101, 102])
    partial = pd.Series([0.5], index=[raw.index[0]])  # only first date has a factor
    adjusted = apply_adjustment(raw, partial)
    assert adjusted["close"].iloc[0] == 50.0
    assert adjusted["close"].iloc[1] == 101.0  # untouched
