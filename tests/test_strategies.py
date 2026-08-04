"""End-to-end: hand-crafted strategies through portfolio -> engine."""

import numpy as np
import pandas as pd
import pytest

from quantlab.backtest.engine import BacktestEngine, simple_returns
from quantlab.factors.portfolio import top_n_long_only
from quantlab.strategies import STRATEGIES


@pytest.fixture
def market():
    idx = pd.bdate_range("2022-01-01", periods=400)
    cols = [f"S{i:02d}" for i in range(20)]
    rng = np.random.default_rng(7)
    close = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0003, 0.02, size=(400, 20)), axis=0),
        index=idx,
        columns=cols,
    )
    volume = pd.DataFrame(
        rng.lognormal(12, 0.5, size=(400, 20)), index=idx, columns=cols
    )
    return close, volume


def _alpha(name, close, volume):
    fn, needs_vol = STRATEGIES[name]
    return fn(close, volume) if needs_vol else fn(close)


@pytest.mark.parametrize("name", list(STRATEGIES))
def test_strategy_runs_end_to_end(name, market):
    close, volume = market
    alpha = _alpha(name, close, volume)

    weights = top_n_long_only(alpha, n_positions=5)
    # long-only, no leverage: each row sums to <= 1 and has no negatives
    assert (weights.sum(axis=1) <= 1.0 + 1e-9).all()
    assert (weights.values >= -1e-12).all()

    res = BacktestEngine().run(weights, simple_returns(close))
    assert np.isfinite(res.equity.iloc[-1])
    assert len(res.equity) == len(close)
    # cost drag is non-negative (costs only ever reduce net vs gross)
    assert res.total_cost_drag >= -1e-9


@pytest.mark.parametrize("name", list(STRATEGIES))
def test_strategy_has_no_lookahead(name, market):
    close, volume = market
    cut = 300
    base = _alpha(name, close, volume)

    c2, v2 = close.copy(), volume.copy()
    c2.iloc[cut + 1 :] *= 3.0
    v2.iloc[cut + 1 :] *= 5.0
    after = _alpha(name, c2, v2)

    pd.testing.assert_frame_equal(
        base.iloc[: cut + 1], after.iloc[: cut + 1], check_exact=False
    )
