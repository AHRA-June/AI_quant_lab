"""Point-in-time factor primitives — correctness and the no-look-ahead audit."""

import numpy as np
import pandas as pd
import pytest

from quantlab.factors import primitives as P


@pytest.fixture
def panel():
    idx = pd.bdate_range("2024-01-01", periods=30)
    cols = ["A", "B", "C", "D"]
    rng = np.random.default_rng(0)
    return pd.DataFrame(rng.normal(100, 5, size=(30, 4)), index=idx, columns=cols)


# --- correctness -----------------------------------------------------------


def test_delay_and_delta(panel):
    assert P.delay(panel, 1).iloc[5].equals(panel.iloc[4])
    d = P.delta(panel, 2)
    assert np.allclose(d.iloc[10].values, (panel.iloc[10] - panel.iloc[8]).values)


def test_returns(panel):
    r = P.returns(panel, 1)
    assert np.allclose(r.iloc[3].values, (panel.iloc[3] / panel.iloc[2] - 1).values)


def test_ts_mean_matches_manual(panel):
    m = P.ts_mean(panel, 5)
    assert np.isnan(m.iloc[3]).all()  # not enough history
    assert np.allclose(m.iloc[4].values, panel.iloc[0:5].mean().values)


def test_cross_sectional_rank_is_within_row(panel):
    r = P.rank(panel)
    # each row's ranks are a permutation of {0.25,0.5,0.75,1.0} for 4 names
    for _, row in r.iterrows():
        assert np.allclose(sorted(row.values), [0.25, 0.5, 0.75, 1.0])


def test_scale_normalizes_abs_sum(panel):
    s = P.scale(P.cs_demean(panel))
    assert np.allclose(s.abs().sum(axis=1).values, 1.0)


def test_delay_rejects_forward():
    with pytest.raises(ValueError):
        P.delay(pd.DataFrame({"A": [1, 2]}), -1)


# --- the decisive property: no operator may look forward -------------------


@pytest.mark.parametrize(
    "op",
    [
        lambda x: P.delay(x, 2),
        lambda x: P.delta(x, 3),
        lambda x: P.returns(x, 1),
        lambda x: P.ts_mean(x, 5),
        lambda x: P.ts_std(x, 5),
        lambda x: P.ts_rank(x, 5),
        lambda x: P.ts_zscore(x, 5),
        lambda x: P.ts_min(x, 4),
        lambda x: P.ts_max(x, 4),
    ],
)
def test_no_lookahead(panel, op):
    """Mutating the future must not change any past output.

    Compute op on the full panel, then corrupt everything after cut and confirm
    outputs up to `cut` are byte-identical. This structurally proves the
    operator only uses trailing data.
    """
    cut = 20
    base = op(panel)

    corrupted = panel.copy()
    corrupted.iloc[cut + 1 :] = corrupted.iloc[cut + 1 :] * 1000.0 + 7.0
    after = op(corrupted)

    pd.testing.assert_frame_equal(base.iloc[: cut + 1], after.iloc[: cut + 1])


def test_operator_registry_exposed():
    # The M2 whitelist parser binds exactly these names.
    assert "ts_mean" in P.OPERATORS and "rank" in P.OPERATORS
    assert all(callable(f) for f in P.OPERATORS.values())
