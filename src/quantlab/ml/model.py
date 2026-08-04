"""Rank-regression models (F3.6).

`LGBMRankModel` is the intended model (gradient-boosted trees suit tabular
cross-sectional features and run comfortably on 2 cores / 8 GB). `RidgeRankModel`
is a dependency-free numpy baseline so the pipeline and tests run without
LightGBM installed. Both implement the `RankModel` protocol.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class RankModel(Protocol):
    def fit(self, X: np.ndarray, y: np.ndarray) -> "RankModel": ...
    def predict(self, X: np.ndarray) -> np.ndarray: ...


class RidgeRankModel:
    """Standardized ridge regression via the closed-form normal equations."""

    def __init__(self, alpha: float = 1.0) -> None:
        self.alpha = alpha
        self._mean: np.ndarray | None = None
        self._std: np.ndarray | None = None
        self._coef: np.ndarray | None = None
        self._intercept: float = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "RidgeRankModel":
        self._mean = X.mean(axis=0)
        self._std = X.std(axis=0)
        self._std[self._std == 0] = 1.0
        Xs = (X - self._mean) / self._std
        n_features = Xs.shape[1]
        A = Xs.T @ Xs + self.alpha * np.eye(n_features)
        self._coef = np.linalg.solve(A, Xs.T @ (y - y.mean()))
        self._intercept = float(y.mean())
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._coef is None:
            raise RuntimeError("model not fitted")
        Xs = (X - self._mean) / self._std
        return Xs @ self._coef + self._intercept


class LGBMRankModel:
    """LightGBM regression on the cross-sectional rank target (lazy import)."""

    def __init__(self, **params) -> None:
        self.params = {
            "n_estimators": 300,
            "learning_rate": 0.03,
            "num_leaves": 31,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "min_child_samples": 50,
            "verbosity": -1,
            **params,
        }
        self._model = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LGBMRankModel":
        try:
            from lightgbm import LGBMRegressor  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - env dependent
            raise ImportError(
                "lightgbm is required for LGBMRankModel. Install: pip install '.[ml]'"
            ) from exc
        self._model = LGBMRegressor(**self.params).fit(X, y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("model not fitted")
        return self._model.predict(X)
