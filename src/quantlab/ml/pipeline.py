"""Walk-forward training → out-of-sample prediction panel.

Trains a fresh model per fold on that fold's (embargoed) training rows and
predicts its test block. The concatenated OOS predictions form a
dates x tickers panel that can be fed to the backtest engine or scored with
Rank IC — every prediction is genuinely out-of-sample.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from quantlab.ml.dataset import build_dataset, predictions_to_panel
from quantlab.ml.model import RankModel, RidgeRankModel
from quantlab.ml.split import walk_forward_folds

ModelFactory = Callable[[], RankModel]


def walk_forward_predict(
    features: dict[str, pd.DataFrame],
    label: pd.DataFrame,
    *,
    model_factory: ModelFactory = RidgeRankModel,
    n_folds: int = 4,
    embargo: int = 5,
    min_train: int | None = None,
) -> pd.DataFrame:
    """Return an out-of-sample prediction panel (dates x tickers)."""
    ds = build_dataset(features, label)
    folds = walk_forward_folds(
        ds.dates, n_folds=n_folds, embargo=embargo, min_train=min_train
    )
    if not folds:
        raise ValueError("no walk-forward folds — need more history or fewer folds")

    all_dates, all_tickers, all_preds = [], [], []
    for fold in folds:
        train_set = set(fold.train_dates)
        test_set = set(fold.test_dates)
        train_mask = np.array([d in train_set for d in ds.dates])
        test_mask = np.array([d in test_set for d in ds.dates])
        if train_mask.sum() == 0 or test_mask.sum() == 0:
            continue

        model = model_factory().fit(ds.X[train_mask], ds.y[train_mask])
        preds = model.predict(ds.X[test_mask])

        all_dates.append(ds.dates[test_mask])
        all_tickers.append(ds.tickers[test_mask])
        all_preds.append(preds)

    return predictions_to_panel(
        np.concatenate(all_dates),
        np.concatenate(all_tickers),
        np.concatenate(all_preds),
    )
