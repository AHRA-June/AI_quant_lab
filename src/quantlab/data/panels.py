"""Assemble per-ticker adjusted series into aligned market panels.

The bridge from the M0 data layer to the M1+ pipeline: pull adjusted OHLCV for
each ticker via the read-through :class:`~quantlab.data.cache.PriceStore` (raw +
factor, adjusted at read time — DQ.1), then align them into ``dates x tickers``
panels keyed by field. These panels are exactly the evaluation context the DSL
parser and the ML feature builder consume, so real KRX data flows through the
same code paths as the synthetic demos.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from quantlab.data.cache import PriceStore
from quantlab.types import OHLCV_COLUMNS


def adjusted_panels(
    store: PriceStore, tickers: list[str], start: date, end: date
) -> dict[str, pd.DataFrame]:
    """Return ``{field: dates x tickers}`` panels of adjusted prices/volume.

    Series are aligned on the union of trading dates; a ticker missing a date
    (late listing, halt) shows NaN there — the downstream universe mask and the
    long-only weighting handle those gaps.
    """
    per_field: dict[str, dict[str, pd.Series]] = {f: {} for f in OHLCV_COLUMNS}
    for ticker in tickers:
        adj = store.get_adjusted(ticker, start, end)
        for field in OHLCV_COLUMNS:
            if field in adj.columns:
                per_field[field][ticker] = adj[field]

    panels: dict[str, pd.DataFrame] = {}
    for field, cols in per_field.items():
        df = pd.DataFrame(cols).sort_index() if cols else pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        panels[field] = df
    return panels
