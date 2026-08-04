"""Assemble feature panels + label into a long-format training matrix.

Each row is one (date, ticker) observation. Only rows where every feature and
the label are present survive — so early history (before rolling windows warm
up) and the last ``horizon`` days (no forward return yet) drop out naturally.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Dataset:
    X: np.ndarray            # (n_obs, n_features)
    y: np.ndarray            # (n_obs,)
    dates: np.ndarray        # (n_obs,) datetime64 — the observation date
    tickers: np.ndarray      # (n_obs,) ticker per row
    feature_names: list[str]

    def __len__(self) -> int:
        return len(self.y)


def build_dataset(features: dict[str, pd.DataFrame], label: pd.DataFrame) -> Dataset:
    """Stack aligned feature panels + label into long-format arrays."""
    names = list(features)
    # Align everything on the common index/columns.
    idx = label.index
    cols = label.columns
    stacked = {n: features[n].reindex(index=idx, columns=cols) for n in names}

    feat_long = pd.DataFrame(
        {n: stacked[n].stack(future_stack=True) for n in names}
    )
    y_long = label.stack(future_stack=True).rename("y")
    joined = feat_long.join(y_long, how="inner").dropna()

    mi = joined.index  # MultiIndex (date, ticker)
    return Dataset(
        X=joined[names].to_numpy(dtype=float),
        y=joined["y"].to_numpy(dtype=float),
        dates=mi.get_level_values(0).to_numpy(),
        tickers=mi.get_level_values(1).to_numpy(),
        feature_names=names,
    )


def predictions_to_panel(
    dates: np.ndarray, tickers: np.ndarray, preds: np.ndarray
) -> pd.DataFrame:
    """Scatter long-format predictions back into a dates x tickers panel."""
    s = pd.Series(preds, index=pd.MultiIndex.from_arrays([dates, tickers]))
    panel = s.unstack()
    panel.index = pd.to_datetime(panel.index)
    return panel.sort_index()
