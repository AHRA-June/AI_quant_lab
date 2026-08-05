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
    n_days: int = 500, n_tickers: int = 30, seed: int = 42, mu_spread: float = 0.0
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Deterministic synthetic close/volume panels.

    ``mu_spread`` > 0 injects a persistent per-ticker drift, so trailing
    momentum genuinely predicts forward returns — used to show the pipeline
    detecting a real signal (vs. structureless data, which it discards).
    """
    idx = pd.bdate_range("2021-01-01", periods=n_days)
    cols = [f"S{i:02d}" for i in range(n_tickers)]
    rng = np.random.default_rng(seed)
    mu = mu_spread * rng.standard_normal(n_tickers)
    daily = mu[None, :] + rng.normal(0.0004, 0.02, size=(n_days, n_tickers))
    close = pd.DataFrame(100 * np.cumprod(1 + daily, axis=0), index=idx, columns=cols)
    volume = pd.DataFrame(
        rng.lognormal(12, 0.6, size=(n_days, n_tickers)), index=idx, columns=cols
    )
    return close, volume


def run_comparison(out_dir: Path) -> dict:
    """Run all hand-crafted strategies, then assess the SELECTION with PBO + DSR.

    PBO and the Deflated Sharpe only make sense across many candidates, so this
    is where they live: a comparison report over the strategy set, with the
    overfitting verdict on picking the in-sample best.
    """
    from quantlab.integrity.dsr import deflated_sharpe_ratio
    from quantlab.integrity.pbo import probability_of_backtest_overfitting
    from quantlab.report.report import StrategyRow, write_comparison_report

    close, volume = synthetic_market(n_days=500, n_tickers=30, seed=1, mu_spread=0.002)
    rets = simple_returns(close)
    eng = BacktestEngine()

    rows: list[StrategyRow] = []
    ret_matrix: dict[str, pd.Series] = {}
    for name, (fn, needs_vol) in STRATEGIES.items():
        alpha = fn(close, volume) if needs_vol else fn(close)
        weights = top_n_long_only(alpha, n_positions=10)
        res = eng.run(weights, rets)
        stats = summary(res.returns, res.equity, res.turnover)
        stats["cost_drag"] = res.total_cost_drag
        rows.append(StrategyRow(label=name, stats=stats, equity=res.equity))
        ret_matrix[name] = res.returns

    perf = pd.DataFrame(ret_matrix).dropna()
    pbo = probability_of_backtest_overfitting(perf, n_blocks=8)

    # DSR of the in-sample best, deflated by the number of candidate strategies.
    per_obs = perf.mean() / perf.std().replace(0, np.nan)
    best = per_obs.idxmax()
    dsr = deflated_sharpe_ratio(
        float(per_obs[best]),
        n_trials=perf.shape[1],
        var_sharpe=float(per_obs.var()),
        n_obs=len(perf),
        skew=float(perf[best].skew()),
        kurtosis=float(perf[best].kurt() + 3.0),  # pandas kurt is excess
    )
    path = write_comparison_report(
        rows, pbo=pbo, dsr=dsr,
        subtitle=f"{len(rows)} strategies · synthetic data · best={best}",
        out_dir=out_dir,
    )
    return {"pbo": pbo, "dsr": dsr, "best": best, "n": len(rows), "report": path}


def run_ml_demo(trials_path: Path, n_shuffles: int = 50) -> dict:
    """M3 end-to-end on synthetic data WITH an injected cross-sectional signal.

    Walk-forward train -> OOS rank predictions -> evaluate (Rank IC) -> use the
    predictions as an alpha through the M1 backtest + integrity pipeline. Because
    the signal is real, it should survive the shuffle control (contrast with
    ``run_demo`` on structureless data, which is discarded).
    """
    from quantlab.factors.portfolio import top_n_long_only
    from quantlab.ml.evaluate import evaluate_predictions
    from quantlab.ml.features import build_features
    from quantlab.ml.labels import forward_return, rank_label
    from quantlab.ml.pipeline import walk_forward_predict

    close, volume = synthetic_market(n_days=500, n_tickers=40, seed=1, mu_spread=0.004)
    feats = build_features(close, volume)
    fwd = forward_return(close, horizon=5)
    pred = walk_forward_predict(feats, rank_label(fwd), n_folds=3, embargo=5)

    ml = evaluate_predictions(pred, fwd)
    weights = top_n_long_only(pred, n_positions=10)
    out = _evaluate(pred, weights, close, trials_path, n_shuffles, label="ml_rank_model")
    out["ml"] = ml
    out["report"] = write_strategy_report(
        out, close, trials_path.parent / "ml_rank_model"
    )
    return out


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
        "equity": res.equity,
        "returns": res.returns,
    }


def write_strategy_report(out: dict, close: pd.DataFrame, out_dir, commentary=None,
                          subtitle=None, client=None):
    """Turn an evaluation dict into a self-contained HTML report (M4).

    If ``client`` (an :class:`~quantlab.dsl.llm.LLMClient`) is given and no
    ``commentary`` was passed, an LLM interpretation is generated and embedded.
    Any commentary failure is swallowed — the report is never blocked on the LLM.
    """
    from quantlab.backtest.engine import simple_returns
    from quantlab.report.report import ReportInputs, equal_weight_benchmark, write_report

    bench = equal_weight_benchmark(simple_returns(close))
    inp = ReportInputs(
        label=out["strategy"],
        subtitle=subtitle or f"config {out['config_hash']} · synthetic data",
        stats=out["stats"],
        equity=out["equity"],
        benchmark_equity=bench,
        shuffle=out["shuffle"],
        trials=out["trials_logged"],
        ml=out.get("ml"),
        commentary=commentary,
    )
    if commentary is None and client is not None:
        from quantlab.report.commentary import generate_commentary
        try:
            inp.commentary = generate_commentary(client, inp)
        except Exception:  # noqa: BLE001 — commentary is best-effort, never fatal
            inp.commentary = None
    return write_report(inp, out_dir)
