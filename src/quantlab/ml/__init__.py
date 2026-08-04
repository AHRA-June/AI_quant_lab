"""ML cross-sectional rank prediction (M3).

Reuses the M1 leak-proof primitive library for features (single source of
truth, shared with the M2 DSL), predicts the **cross-sectional rank** of forward
returns via a rank-regression model, and evaluates with Rank IC / IC IR /
quantile spread. Walk-forward validation enforces a forward-horizon **embargo**
so overlapping labels cannot leak across the train/test boundary (F3.4).
"""

from quantlab.ml.features import FEATURES, build_features
from quantlab.ml.labels import forward_return, rank_label
from quantlab.ml.pipeline import walk_forward_predict
from quantlab.ml.split import walk_forward_folds

__all__ = [
    "FEATURES",
    "build_features",
    "forward_return",
    "rank_label",
    "walk_forward_folds",
    "walk_forward_predict",
]
