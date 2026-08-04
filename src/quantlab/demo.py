"""End-to-end M1 pipeline on synthetic data.

Wires every M1 piece together so the whole core can be exercised without live
KRX access: hand-crafted strategy → target weights → backtest → metrics →
shuffle control → automatic trial logging. Driven by ``quantlab demo``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from quantlab.backtest.engine import BacktestEngine, simple_returns
from quantlab.backtest.metrics import ic_ir, rank_ic, sharpe, summary
from quantlab.data.cache import content_hash
from quantlab.factors.portfolio import top_n_long_only
from quantlab.integrity.shuffle import shuffle_pvalue
from quantlab.integrity.trials import TrialLog
from quantlab.strategies import STRATEGIES


def synthetic_market(
    n_days: int = 500, n_tickers: int = 30, seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Deterministic synthetic close/volume panels."""
    idx = pd.bdate_range("2021-01-01", periods=n_days)
    cols = [f"S{i:02d}" for i in range(n_tickers)]
    rng = np.random.default_rng(seed)
    close = pd.DataFrame(
        100 * np.cumprod(1 + rng.normal(0.0004, 0.02, size=(n_days, n_tickers)), axis=0),
        index=idx,
        columns=cols,
    )
    volume = pd.DataFrame(
        rng.lognormal(12, 0.6, size=(n_days, n_tickers)), index=idx, columns=cols
    )
    return close, volume


def run_demo(strategy: str, n_positions: int, trials_path: Path, n_shuffles: int = 50) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; choose from {list(STRATEGIES)}")

    close, volume = synthetic_market()
    fn, needs_vol = STRATEGIES[strategy]
    alpha = fn(close, volume) if needs_vol else fn(close)
    weights = top_n_long_only(alpha, n_positions=n_positions)
    return _evaluate(alpha, weights, close, trials_path, n_shuffles, label=strategy)


def run_config(config, trials_path: Path, n_shuffles: int = 50) -> dict:
    """Evaluate a :class:`~quantlab.dsl.config.StrategyConfig` end-to-end (M2 → M1).

    Compiles the DSL alpha, builds weights per the portfolio config, and runs the
    same backtest + integrity pipeline as :func:`run_demo`, on synthetic data.
    """
    from quantlab.dsl.runner import strategy_weights
    from quantlab.dsl.parser import compile_alpha

    close, volume = synthetic_market()
    context = {
        "open": close, "high": close, "low": close, "close": close,
        "volume": volume, "value": close * volume,
    }
    alpha = compile_alpha(config.alpha)(context)
    weights = strategy_weights(config, context)
    return _evaluate(alpha, weights, close, trials_path, n_shuffles, label=config.content_hash())


def _evaluate(alpha, weights, close, trials_path: Path, n_shuffles: int, label: str) -> dict:
    """Shared pipeline: weights → backtest → metrics → shuffle control → trial log."""
    rets = simple_returns(close)
    res = BacktestEngine().run(weights, rets)

    stats = summary(res.returns, res.equity, res.turnover)
    stats["cost_drag"] = res.total_cost_drag

    # Shuffle control (F7.4): does the signal beat a cross-sectionally shuffled null?
    fwd = rets.shift(-1)  # next-day forward returns (evaluation only, not traded)

    def mean_ic(sig: pd.DataFrame) -> float:
        return float(rank_ic(sig, fwd).mean())

    shuf = shuffle_pvalue(alpha, mean_ic, n_shuffles=n_shuffles, seed=0)
    daily_ic = rank_ic(alpha, fwd)

    config_hash = content_hash(weights)
    log = TrialLog(trials_path)
    with log.run(config_hash, meta={"label": label}) as r:
        r["metrics"] = {
            "sharpe": stats["sharpe"],
            "ic_ir": ic_ir(daily_ic),
            "shuffle_p": shuf.p_value,
        }

    return {
        "strategy": label,
        "config_hash": config_hash,
        "stats": stats,
        "ic_mean": float(daily_ic.mean()),
        "ic_ir": ic_ir(daily_ic),
        "shuffle": shuf,
        "trials_logged": log.count(),
    }
