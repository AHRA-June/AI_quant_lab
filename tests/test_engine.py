"""Backtest engine validation (F4.7) — the M1 completion gate.

Two layers:
  (a) golden-value: hand-computed 3×5 and single-name cases pin down the exact
      t+1 / drift / cost arithmetic.
  (b) index reconstruction: a cap-weighted daily-rebalanced portfolio must
      exactly reproduce the independently computed cap-weighted index.
"""

import numpy as np
import pandas as pd
import pytest

from quantlab.backtest.engine import BacktestEngine, simple_returns
from quantlab.config import CostModel

IDX = pd.bdate_range("2024-01-01", periods=5)
COLS = ["A", "B", "C"]


def _returns(rows):
    return pd.DataFrame(rows, index=IDX, columns=COLS)


# --- (a) golden values -----------------------------------------------------


def test_golden_zero_cost_returns_and_equity():
    rets = _returns(
        [
            [0.00, 0.00, 0.00],
            [0.10, 0.00, -0.05],
            [0.00, 0.20, 0.00],
            [-0.10, 0.10, 0.10],
            [0.05, 0.05, 0.05],
        ]
    )
    tw = pd.DataFrame(np.nan, index=IDX, columns=COLS)
    tw.iloc[0] = [0.5, 0.5, 0.0]  # signal at d0 → held from d1 (t+1)

    eng = BacktestEngine(cost=CostModel(commission_bps=0, slippage_bps=0, sell_tax_bps=0))
    res = eng.run(tw, rets)

    # Hand-computed daily portfolio returns (cash for C weight 0).
    assert np.allclose(res.returns.values, [0.0, 0.05, 0.10, 0.0, 0.05])
    assert np.allclose(res.gross_equity.values, [1.0, 1.05, 1.155, 1.155, 1.21275])
    # Turnover: buy-in at d1, then small rebalances against drift.
    assert res.turnover.iloc[1] == pytest.approx(1.0)
    assert res.turnover.iloc[2] == pytest.approx(0.047619047, abs=1e-6)
    assert res.turnover.iloc[3] == pytest.approx(0.090909090, abs=1e-6)
    assert res.turnover.iloc[4] == pytest.approx(0.10, abs=1e-9)


def test_golden_buy_cost_exact():
    idx = pd.bdate_range("2024-01-01", periods=2)
    rets = pd.DataFrame({"A": [0.0, 0.10]}, index=idx)
    tw = pd.DataFrame({"A": [1.0, np.nan]}, index=idx)  # buy at d0 → filled d1

    eng = BacktestEngine(cost=CostModel(commission_bps=10, slippage_bps=5, sell_tax_bps=20))
    res = eng.run(tw, rets)

    # d1: buy turnover 1.0 → cost = 1.0*(10+5)/1e4 = 0.0015 (no sell tax on a buy)
    assert res.cost.iloc[1] == pytest.approx(0.0015)
    assert res.returns.iloc[1] == pytest.approx((1.10) * (1 - 0.0015) - 1)
    assert res.gross_equity.iloc[1] == pytest.approx(1.10)


def test_golden_sell_tax_on_exit():
    idx = pd.bdate_range("2024-01-01", periods=4)
    rets = pd.DataFrame({"A": [0.0, 0.0, 0.0, 0.0]}, index=idx)
    tw = pd.DataFrame({"A": [1.0, np.nan, 0.0, np.nan]}, index=idx)  # in at d1, out at d3

    eng = BacktestEngine(cost=CostModel(commission_bps=10, slippage_bps=5, sell_tax_bps=20))
    res = eng.run(tw, rets)

    assert res.cost.iloc[1] == pytest.approx(0.0015)  # buy: (10+5)/1e4
    assert res.cost.iloc[2] == pytest.approx(0.0)     # hold, no trade
    assert res.cost.iloc[3] == pytest.approx(0.0035)  # sell: (10+5+20)/1e4


def test_execution_lag_prevents_same_day_fill():
    # A signal at d0 must NOT earn d0's return (t+1 rule, F4.3).
    rets = _returns([[0.5, 0.5, 0.5], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0]])
    tw = pd.DataFrame(np.nan, index=IDX, columns=COLS)
    tw.iloc[0] = [1.0, 0.0, 0.0]

    eng = BacktestEngine(cost=CostModel(commission_bps=0, slippage_bps=0, sell_tax_bps=0))
    res = eng.run(tw, rets)
    assert res.returns.iloc[0] == 0.0  # no position on the signal day


def test_execution_lag_must_be_positive():
    with pytest.raises(ValueError):
        BacktestEngine(execution_lag=0)


# --- (b) index reconstruction ---------------------------------------------


def test_reconstructs_cap_weighted_index_exactly():
    idx = pd.bdate_range("2024-01-01", periods=40)
    rng = np.random.default_rng(1)
    cols = [f"S{i}" for i in range(8)]
    prices = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0, 0.01, size=(40, 8)), axis=0),
        index=idx,
        columns=cols,
    )
    rets = simple_returns(prices)

    caps = pd.Series(rng.uniform(1, 10, size=8), index=cols)
    w0 = caps / caps.sum()

    tw = pd.DataFrame(
        np.broadcast_to(w0.values, (len(idx), 8)), index=idx, columns=cols
    )
    eng = BacktestEngine(cost=CostModel(commission_bps=0, slippage_bps=0, sell_tax_bps=0))
    res = eng.run(tw, rets)

    # Independently: daily-rebalanced cap-weighted index (engine holds from d1).
    expected = (1 + rets.dot(w0)).cumprod()
    expected.iloc[0] = 1.0  # engine has no position on the first (lagged) day
    assert np.allclose(res.gross_equity.values, expected.values, rtol=1e-12, atol=1e-12)
