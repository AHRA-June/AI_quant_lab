"""Compile a :class:`StrategyConfig` into target weights for the engine.

Ties the M2 DSL to the M1 core: evaluate the alpha expression against a market
context (the six field panels), turn the alpha into long-only top-N weights,
and thin to the configured rebalance cadence. The result feeds straight into
:class:`quantlab.backtest.engine.BacktestEngine`.
"""

from __future__ import annotations

import pandas as pd

from quantlab.dsl.config import StrategyConfig
from quantlab.dsl.parser import Context, compile_alpha
from quantlab.factors.portfolio import apply_rebalance, top_n_long_only


def strategy_weights(config: StrategyConfig, context: Context) -> pd.DataFrame:
    """Alpha expression + portfolio config → target-weight matrix."""
    alpha = compile_alpha(config.alpha)(context)
    weights = top_n_long_only(
        alpha,
        n_positions=config.portfolio.n_positions,
        weighting=config.portfolio.weighting,
    )
    return apply_rebalance(weights, config.portfolio.rebalance)
