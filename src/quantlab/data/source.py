"""``DataSource`` — the abstraction that decouples the whole system from any
single vendor (F1.3).

The MVP ships a pykrx-backed implementation. A brokerage API (e.g. 한국투자증권)
for live/real trading can later implement this same interface without touching
the cache, universe, engine, or reporting layers.

Contract notes
--------------
* ``get_ohlcv`` returns **raw, unadjusted** OHLCV. Adjustment is applied at
  read time from a separately stored factor series (DQ.1) — never baked into
  what a source hands back.
* ``get_ticker_list(on)`` is point-in-time: the tickers actually listed *on
  that date*. This is what makes survivorship-bias-free universe
  reconstruction possible (§11).
* All price/OHLCV frames are indexed by ``pandas.DatetimeIndex`` and use the
  canonical columns in :data:`quantlab.types.OHLCV_COLUMNS`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd

from quantlab.types import Market


class DataSource(ABC):
    """Vendor-agnostic market-data interface."""

    @abstractmethod
    def get_ticker_list(self, on: date, market: Market) -> list[str]:
        """Tickers listed on ``market`` as of ``on`` (point-in-time)."""

    @abstractmethod
    def get_etf_etn_ticker_list(self, on: date) -> list[str]:
        """ETF/ETN tickers as of ``on`` — subtracted during universe filtering (DQ.3)."""

    @abstractmethod
    def get_ticker_name(self, ticker: str, on: date | None = None) -> str:
        """Human-readable security name (used by name-pattern filters, DQ.3)."""

    @abstractmethod
    def get_ohlcv(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """**Raw** (unadjusted) daily OHLCV for ``ticker`` in ``[start, end]``.

        Returns a frame indexed by date with columns
        ``open, high, low, close, volume, value``.
        """

    @abstractmethod
    def get_adjusted_close(self, ticker: str, start: date, end: date) -> pd.Series:
        """Adjusted close series for ``ticker`` — used only to *derive* the
        adjustment factor (raw stays the source of truth, DQ.1)."""

    @abstractmethod
    def get_market_cap(self, on: date, market: Market) -> pd.DataFrame:
        """Per-ticker market cap on ``on``.

        Returns a frame indexed by ticker with at least a ``mktcap`` column.
        """
