"""ML cross-sectional rank prediction (M3)."""

import numpy as np
import pandas as pd
import pytest

from quantlab.ml.dataset import build_dataset
from quantlab.ml.evaluate import evaluate_predictions
from quantlab.ml.features import build_features
from quantlab.ml.labels import forward_return, rank_label
from quantlab.ml.model import RankModel, RidgeRankModel
from quantlab.ml.pipeline import walk_forward_predict
from quantlab.ml.split import walk_forward_folds


def _market(n_days=400, n_tickers=25, mu_spread=0.0, seed=0):
    """Synthetic market. mu_spread>0 injects a persistent cross-sectional drift
    so trailing momentum genuinely predicts forward returns."""
    idx = pd.bdate_range("2021-01-01", periods=n_days)
    cols = [f"S{i:02d}" for i in range(n_tickers)]
    rng = np.random.default_rng(seed)
    mu = mu_spread * rng.standard_normal(n_tickers)  # per-ticker drift
    daily = mu[None, :] + 0.012 * rng.standard_normal((n_days, n_tickers))
    close = pd.DataFrame(100 * np.cumprod(1 + daily, axis=0), index=idx, columns=cols)
    volume = pd.DataFrame(rng.lognormal(12, 0.5, (n_days, n_tickers)), index=idx, columns=cols)
    return close, volume


# --- labels ----------------------------------------------------------------


def test_forward_return_looks_forward_and_tail_is_nan():
    close, _ = _market()
    fwd = forward_return(close, 5)
    assert fwd.iloc[-5:].isna().all().all()  # no future beyond the last date
    # value at t equals close(t+5)/close(t) - 1
    exp = close.iloc[10] / close.iloc[5] - 1
    assert np.allclose(fwd.iloc[5].values, exp.values)


def test_rank_label_centered():
    close, _ = _market()
    lab = rank_label(forward_return(close, 5))
    row = lab.iloc[100].dropna()
    assert np.isclose(row.min(), -0.5) and np.isclose(row.max(), 0.5)
    assert abs(row.mean()) < 1e-9  # exactly centered


# --- features: no look-ahead ----------------------------------------------


def test_features_have_no_lookahead():
    close, volume = _market()
    cut = 300
    base = build_features(close, volume)

    c2, v2 = close.copy(), volume.copy()
    c2.iloc[cut + 1 :] *= 2.0
    v2.iloc[cut + 1 :] *= 3.0
    after = build_features(c2, v2)

    for name in base:
        pd.testing.assert_frame_equal(
            base[name].iloc[: cut + 1], after[name].iloc[: cut + 1]
        )


# --- walk-forward embargo --------------------------------------------------


def test_folds_enforce_embargo_gap():
    dates = pd.bdate_range("2021-01-01", periods=200).to_numpy()
    folds = walk_forward_folds(dates, n_folds=4, embargo=5, min_train=100)
    assert folds
    uniq = np.array(sorted(set(dates)))
    pos = {d: i for i, d in enumerate(uniq)}
    for f in folds:
        gap = pos[f.test_dates[0]] - pos[f.train_dates[-1]]
        assert gap >= 5  # embargo respected
        assert f.train_dates[-1] < f.test_dates[0]


def test_no_folds_when_history_too_short():
    dates = pd.bdate_range("2021-01-01", periods=6).to_numpy()
    assert walk_forward_folds(dates, n_folds=4, embargo=5, min_train=3) == []


# --- dataset ---------------------------------------------------------------


def test_dataset_drops_nan_and_shapes_align():
    close, volume = _market(n_days=120)
    feats = build_features(close, volume)
    ds = build_dataset(feats, rank_label(forward_return(close, 5)))
    assert ds.X.shape[0] == len(ds.y) == len(ds.dates) == len(ds.tickers)
    assert ds.X.shape[1] == len(feats)
    assert np.isfinite(ds.X).all() and np.isfinite(ds.y).all()


# --- model -----------------------------------------------------------------


def test_ridge_recovers_linear_signal():
    rng = np.random.default_rng(0)
    X = rng.standard_normal((500, 3))
    y = X @ np.array([1.0, -0.5, 0.0]) + 0.1 * rng.standard_normal(500)
    model = RidgeRankModel(alpha=1.0).fit(X, y)
    pred = model.predict(X)
    assert np.corrcoef(pred, y)[0, 1] > 0.9
    assert isinstance(model, RankModel)


# --- the M3 gate: out-of-sample signal recovery ----------------------------


def test_walkforward_recovers_real_signal_and_rejects_noise():
    # With a persistent per-ticker drift, trailing momentum predicts forward
    # returns -> OOS Rank IC should be clearly positive (measured ~0.25).
    close, volume = _market(n_days=500, n_tickers=40, mu_spread=0.002, seed=1)
    feats = build_features(close, volume)
    fwd = forward_return(close, 5)
    pred = walk_forward_predict(feats, rank_label(fwd), n_folds=3, embargo=5)
    signal = evaluate_predictions(pred, fwd)
    assert signal["rank_ic_mean"] > 0.10  # genuinely predictive, out-of-sample
    assert signal["quantile_spread"] > 0  # top quintile out-returns the bottom

    # No drift -> nothing to predict; OOS Rank IC hugs zero (measured ~0.00).
    close_n, volume_n = _market(n_days=500, n_tickers=40, mu_spread=0.0, seed=2)
    feats_n = build_features(close_n, volume_n)
    fwd_n = forward_return(close_n, 5)
    pred_n = walk_forward_predict(feats_n, rank_label(fwd_n), n_folds=3, embargo=5)
    noise = evaluate_predictions(pred_n, fwd_n)
    assert abs(noise["rank_ic_mean"]) < 0.06
