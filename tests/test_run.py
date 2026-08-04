"""Real-data pipeline (DataSource -> panels -> backtest -> report), via a fake."""

from datetime import date

import pandas as pd

from quantlab.data.cache import OHLCVCache, PriceStore
from quantlab.data.panels import adjusted_panels
from quantlab.dsl.config import StrategyConfig
from quantlab.run import run_backtest
from quantlab.types import OHLCV_COLUMNS
from tests.fakes import RichFakeDataSource

START, END = date(2021, 7, 1), date(2022, 12, 31)

CONFIG = StrategyConfig.from_yaml(
    'alpha: "rank(returns(close, 20)) * rank(ts_mean(volume, 5) / ts_mean(volume, 20))"\n'
    "universe: {market: [KOSPI], top_mktcap: 20, min_turnover: 1e8}\n"
    "portfolio: {n_positions: 5, weighting: equal, rebalance: weekly}\n"
)


def test_adjusted_panels_align_across_tickers(tmp_path):
    src = RichFakeDataSource()
    store = PriceStore(src, OHLCVCache(tmp_path))
    panels = adjusted_panels(store, src.commons[:10], date(2021, 1, 1), date(2021, 6, 30))

    assert set(panels) == set(OHLCV_COLUMNS)
    close = panels["close"]
    assert close.shape[1] == 10  # one column per ticker
    assert isinstance(close.index, pd.DatetimeIndex)
    assert (close.dropna() > 0).all().all()


def test_run_backtest_end_to_end_writes_report(tmp_path):
    src = RichFakeDataSource()
    out = run_backtest(
        src, CONFIG, start=START, end=END,
        cache_dir=tmp_path / "cache", out_dir=tmp_path / "exp", n_shuffles=20,
    )
    # universe: 30 commons, preferred + ETF excluded, top-20 by cap
    assert out["universe_size"] == 20
    assert out["report"].exists()
    html = out["report"].read_text()
    assert "AI Quant Lab" in html and "Research integrity" in html
    # backtest produced a finite equity curve and standard metrics
    import numpy as np
    assert np.isfinite(out["equity"].iloc[-1])
    assert {"sharpe", "max_drawdown", "cagr"} <= set(out["stats"])
    assert out["trials_logged"] >= 1

    # the evaluation window must actually span [START, END] — not collapse to a
    # single point because the universe liquidity pass warmed the cache narrow.
    eq = out["equity"]
    assert eq.index.min() <= pd.Timestamp(START)
    assert eq.index.max() >= pd.Timestamp(2022, 12, 1)
    assert len(eq) > 300  # ~18 months of trading days, not one


def test_run_backtest_rejects_empty_universe(tmp_path):
    src = RichFakeDataSource()
    # min_turnover impossibly high -> everything filtered out
    cfg = StrategyConfig.from_yaml(
        'alpha: "rank(returns(close, 20))"\n'
        "universe: {market: [KOSPI], top_mktcap: 20, min_turnover: 1e15}\n"
    )
    import pytest

    with pytest.raises(ValueError):
        run_backtest(src, cfg, start=START, end=END,
                     cache_dir=tmp_path / "c", out_dir=tmp_path / "o")
