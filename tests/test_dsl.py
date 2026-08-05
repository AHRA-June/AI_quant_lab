"""Factor DSL: whitelist parser, config, and runner (M2)."""

import numpy as np
import pandas as pd
import pytest

from quantlab.dsl.config import StrategyConfig
from quantlab.dsl.parser import DslError, compile_alpha, used_fields, used_operators
from quantlab.dsl.runner import strategy_weights


@pytest.fixture
def ctx():
    idx = pd.bdate_range("2024-01-01", periods=60)
    cols = ["A", "B", "C", "D"]
    rng = np.random.default_rng(0)
    close = pd.DataFrame(100 + rng.normal(0, 5, (60, 4)).cumsum(0), index=idx, columns=cols)
    volume = pd.DataFrame(rng.lognormal(10, 0.5, (60, 4)), index=idx, columns=cols)
    return {
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": volume,
        "value": close * volume,
    }


# --- parsing & evaluation --------------------------------------------------


def test_valid_expression_evaluates(ctx):
    fn = compile_alpha("rank(ts_mean(volume, 5) / ts_mean(volume, 20)) * rank(-delta(close, 20))")
    out = fn(ctx)
    assert isinstance(out, pd.DataFrame)
    assert out.shape == ctx["close"].shape


def test_arithmetic_and_negation(ctx):
    out = compile_alpha("-rank(returns(close, 5)) + 1")(ctx)
    assert out.shape == ctx["close"].shape


def test_used_operators_and_fields():
    expr = "rank(ts_mean(volume, 5)) * scale(returns(close, 20))"
    assert used_operators(expr) == {"rank", "ts_mean", "scale", "returns"}
    assert used_fields(expr) == {"volume", "close"}


@pytest.mark.parametrize(
    "bad",
    [
        "close.shift(-1)",              # attribute/method — look-ahead attempt
        "close.rolling(5).mean()",      # method chain
        "close[0]",                     # subscript
        "unknown_field",                # unknown name
        "frobnicate(close)",            # unknown operator
        "close > 1",                    # compare op
        "close and volume",             # boolean op
        "[x for x in close]",           # comprehension
        "lambda x: x",                  # lambda
        "'string'",                     # string literal
        "__import__('os')",             # call to non-operator
    ],
)
def test_disallowed_constructs_rejected(bad):
    with pytest.raises(DslError):
        compile_alpha(bad)


def test_forward_shift_blocked_at_eval(ctx):
    # delay only looks back; a negative arg is caught by the operator guard.
    with pytest.raises(DslError):
        compile_alpha("delay(close, -1)")(ctx)


def test_scalar_alpha_rejected(ctx):
    with pytest.raises(DslError):
        compile_alpha("1 + 2")(ctx)


# --- config ----------------------------------------------------------------

YAML = """
alpha: "rank(ts_mean(volume, 5) / ts_mean(volume, 20)) * rank(-delta(close, 20))"
universe: {market: [KOSPI, KOSDAQ], top_mktcap: 300, min_turnover: 5e8}
portfolio: {n_positions: 20, weighting: equal, rebalance: weekly}
"""


def test_config_from_yaml_roundtrip():
    cfg = StrategyConfig.from_yaml(YAML)
    assert cfg.portfolio.n_positions == 20
    assert cfg.universe.top_mktcap == 300
    # round-trips through YAML and stays valid
    again = StrategyConfig.from_yaml(cfg.to_yaml())
    assert again.content_hash() == cfg.content_hash()


def test_config_rejects_invalid_alpha():
    with pytest.raises(Exception):
        StrategyConfig.from_yaml('alpha: "close.shift(-1)"')


def test_config_hash_is_content_sensitive():
    a = StrategyConfig.from_yaml(YAML)
    b = StrategyConfig.from_yaml(YAML.replace("n_positions: 20", "n_positions: 10"))
    assert a.content_hash() != b.content_hash()


# --- runner ----------------------------------------------------------------


def test_strategy_weights_long_only_and_rebalanced(ctx):
    cfg = StrategyConfig.from_yaml(
        'alpha: "rank(returns(close, 20))"\n'
        "portfolio: {n_positions: 2, weighting: equal, rebalance: weekly}\n"
    )
    w = strategy_weights(cfg, ctx)
    # long-only, no leverage on the rows that actually hold weights
    held = w.dropna(how="all")
    assert (held.sum(axis=1) <= 1.0 + 1e-9).all()
    assert (held.fillna(0).values >= -1e-12).all()
    # weekly rebalance => far fewer signal rows than trading days
    assert len(held) < len(ctx["close"]) / 3


@pytest.mark.parametrize(
    "freq, min_rows, max_rows",
    [("daily", 60, 60), ("weekly", 10, 14), ("monthly", 3, 3)],
)
def test_apply_rebalance_frequencies(ctx, freq, min_rows, max_rows):
    # Regression: monthly used the resample alias "ME", which to_period rejects.
    from quantlab.factors.portfolio import apply_rebalance, top_n_long_only

    weights = top_n_long_only(compile_alpha("rank(returns(close, 5))")(ctx), 2)
    masked = apply_rebalance(weights, freq)
    reb_rows = masked.dropna(how="all")
    assert min_rows <= len(reb_rows) <= max_rows
    # rebalance dates are the last trading day of each period
    if freq != "daily":
        assert masked.index[-1] in reb_rows.index
