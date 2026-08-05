"""Screen (boolean filter) DSL: compiler + NL generator."""

import numpy as np
import pandas as pd
import pytest

from quantlab.dsl.llm import ScreenGenerator
from quantlab.dsl.parser import DslError
from quantlab.dsl.screen import compile_screen


def _ctx(n_days=40, n_tickers=4, seed=0):
    idx = pd.bdate_range("2024-01-01", periods=n_days)
    cols = [f"T{i}" for i in range(n_tickers)]
    rng = np.random.default_rng(seed)
    close = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0.001, 0.02, (n_days, n_tickers)), 0),
                         index=idx, columns=cols)
    volume = pd.DataFrame(rng.lognormal(12, 0.5, (n_days, n_tickers)), index=idx, columns=cols)
    return {"open": close, "high": close, "low": close, "close": close,
            "volume": volume, "value": close * volume}


def test_screen_evaluates_to_boolean_mask():
    ctx = _ctx()
    mask = compile_screen("close > ts_mean(close, 20) and volume > ts_mean(volume, 20) * 1.5")(ctx)
    assert mask.dtypes.eq(bool).all()
    assert mask.shape == ctx["close"].shape


def test_screen_scalar_and_or_not():
    ctx = _ctx()
    m = compile_screen("returns(close, 5) > 0.05 or not (close < 50)")(ctx)
    assert m.dtypes.eq(bool).all()


@pytest.mark.parametrize("bad", [
    "close == 100",              # equality not allowed
    "close",                     # not a boolean
    "close > 1 < 2",             # chained comparison
    "close.rolling(5)",          # attribute/method
    "close > oops(1)",           # unknown operator
])
def test_screen_rejects_unsafe_or_nonboolean(bad):
    with pytest.raises(DslError):
        compile_screen(bad)


class _FakeScreenLLM:
    def complete(self, system, user):
        return "close > ts_mean(close, 20) and volume > ts_mean(volume, 20) * 2"


def test_screen_generator_returns_validated_expr():
    expr = ScreenGenerator(_FakeScreenLLM()).generate("20일선 위 + 거래량 급증")
    assert "ts_mean(close, 20)" in expr
    compile_screen(expr)  # round-trips through the validator
