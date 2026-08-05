"""End-to-end real-data backtest: DataSource → report.

Ties every layer together on *real* market data (any :class:`DataSource` —
pykrx for live KRX, or a fake in tests):

    1. reconstruct the point-in-time universe (§11)
    2. assemble adjusted OHLCV panels over the window + warm-up (DQ.1)
    3. compile the DSL alpha and build target weights (M2)
    4. backtest with the target-weight engine (M1)
    5. evaluate + write a self-contained report (M4)

The same synthetic-data pipeline the demos exercise, now fed by the data layer.

Universe note (v1): the universe is reconstructed once, as of ``start``. Fully
point-in-time membership *per rebalance date* is a documented refinement — see
PRD §11; the current form still avoids look-ahead in signals and returns.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from quantlab.data.cache import OHLCVCache, PriceStore
from quantlab.data.panels import adjusted_panels
from quantlab.data.source import DataSource
from quantlab.data.universe import UniverseBuilder
from quantlab.dsl.config import StrategyConfig
from quantlab.dsl.parser import compile_alpha
from quantlab.dsl.runner import strategy_weights


def run_backtest(
    source: DataSource,
    config: StrategyConfig,
    *,
    start: date,
    end: date,
    cache_dir: str | Path,
    out_dir: str | Path,
    warmup_days: int = 400,
    n_shuffles: int = 50,
    data_label: str = "real data",
    trials_path: str | Path | None = None,
) -> dict:
    """Run ``config`` on ``source`` over ``[start, end]`` and write a report.

    ``trials_path`` overrides where the run is logged; defaults to
    ``out_dir/trials.jsonl``. Point several runs at one path to keep the
    multiple-testing trial count complete across them (F7.1).
    """
    from quantlab.demo import _evaluate, write_strategy_report  # local: avoids cycle

    store = PriceStore(source, OHLCVCache(cache_dir))

    # 1. point-in-time universe as of `start`
    tickers = UniverseBuilder(source, price_store=store).build(start, config.universe.to_spec())
    if not tickers:
        raise ValueError("empty universe — check date, market, and filters")

    # 2. adjusted panels over [start - warm-up, end]
    fetch_start = start - timedelta(days=warmup_days)
    panels = adjusted_panels(store, tickers, fetch_start, end)
    close = panels["close"]
    if close.empty:
        raise ValueError("no price data assembled for the universe/date range")

    # 3-4. alpha + weights, then slice to the evaluation window (features stay warm)
    alpha_full = compile_alpha(config.alpha)(panels)
    weights_full = strategy_weights(config, panels)
    in_window = close.index >= pd.Timestamp(start)
    alpha = alpha_full.loc[in_window]
    weights = weights_full.loc[in_window]
    close_w = close.loc[in_window]

    # 5. evaluate + report (reuses the M1 backtest + F7 integrity + M4 report)
    trials_path = Path(trials_path) if trials_path else Path(out_dir) / "trials.jsonl"
    out = _evaluate(
        alpha, weights, close_w, trials_path, n_shuffles, label=config.content_hash()
    )
    out["universe_size"] = len(tickers)
    subtitle = (
        f"config {out['config_hash']} · {data_label} · "
        f"{start:%Y-%m-%d}→{end:%Y-%m-%d} · {len(tickers)} names"
    )
    out["report"] = write_strategy_report(out, close_w, out_dir, subtitle=subtitle)
    return out
