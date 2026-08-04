"""Walk-forward validation with an embargo gap (F3.4).

Expanding-window walk-forward: an initial training span, then ``n_folds``
contiguous out-of-sample test blocks. Between a fold's training data and its
test block we drop ``embargo`` dates. This matters specifically for
cross-sectional forward-return labels: the label at train date ``t`` spans
``[t, t+horizon]``, so without an embargo of at least ``horizon`` days the last
training labels overlap the test window and leak future information. Set
``embargo = horizon``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Fold:
    train_dates: np.ndarray
    test_dates: np.ndarray


def walk_forward_folds(
    dates: np.ndarray,
    *,
    n_folds: int = 4,
    embargo: int = 5,
    min_train: int | None = None,
) -> list[Fold]:
    """Return expanding-window folds over the sorted unique ``dates``.

    ``min_train`` defaults to half the timeline. Folds whose training set would
    be empty after the embargo are skipped.
    """
    uniq = np.array(sorted(set(dates)))
    n = len(uniq)
    if min_train is None:
        min_train = n // 2
    if min_train >= n:
        return []

    test_region = uniq[min_train:]
    blocks = np.array_split(test_region, n_folds)

    folds: list[Fold] = []
    for block in blocks:
        if len(block) == 0:
            continue
        test_start_idx = int(np.searchsorted(uniq, block[0]))
        train_end_idx = test_start_idx - embargo  # exclusive
        if train_end_idx <= 0:
            continue
        folds.append(Fold(train_dates=uniq[:train_end_idx], test_dates=block))
    return folds
