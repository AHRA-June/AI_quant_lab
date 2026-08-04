"""File-backed :class:`DataSource` for long-format OHLCV CSVs.

The pykrx source needs live KRX access; this one turns any *already-downloaded*
long CSV — one row per ``(date, ticker)`` — into the same interface, so real
historical data can flow through the identical universe → panel → backtest →
report path the demos and the live source use. It is deliberately **pure**: it
never touches the network, so it stays unit-testable and the fetch step lives in
the caller (see ``examples/run_sp500.py``).

Expected long frame columns::

    date, open, high, low, close, volume, <ticker-col>

``value`` (거래대금) is derived as ``close * volume`` when absent.

Caveats vs. a full vendor feed (documented, not hidden):

* **Adjustment.** Datasets like this ship a single consolidated ``close`` with no
  separate corporate-action factor, so ``get_adjusted_close`` returns that close
  as-is → the derived factor is ~1.0 (adjusted == raw). Splits already folded
  into the vendor's close stay folded in; nothing is re-adjusted.
* **Market cap.** Shares-outstanding is not in a price-only CSV, so
  :meth:`get_market_cap` returns a **trailing-dollar-volume proxy** — a
  size/liquidity stand-in, point-in-time as of the query date. The universe it
  produces is "largest by turnover", not strictly "largest by cap".
* **Market.** :class:`~quantlab.types.Market` is KRX-shaped (KOSPI/KOSDAQ). A
  non-KRX panel is mapped onto a single placeholder market so the KRX-specific
  exclusion filters (Korean name patterns, 6-digit suffix) simply no-op.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from quantlab.data.source import DataSource
from quantlab.types import OHLCV_COLUMNS, Market, as_date

_PRICE_COLS = ("open", "high", "low", "close")


class CsvDataSource(DataSource):
    """Serve OHLCV from an in-memory long-format frame (no network)."""

    def __init__(
        self,
        long_frame: pd.DataFrame,
        *,
        ticker_col: str = "Name",
        market: Market = Market.KOSPI,
        etf_etn: frozenset[str] = frozenset(),
        names: dict[str, str] | None = None,
        mktcap_lookback: int = 60,
    ) -> None:
        self.market = market
        self._etf_etn = frozenset(etf_etn)
        self._names = dict(names or {})
        self._mktcap_lookback = mktcap_lookback

        df = long_frame.rename(columns={ticker_col: "ticker"}).copy()
        missing = {"date", "close", "volume", "ticker"} - set(df.columns)
        if missing:
            raise ValueError(f"long_frame missing required columns: {sorted(missing)}")
        df["date"] = pd.to_datetime(df["date"])
        df["ticker"] = df["ticker"].astype(str)
        # Fill any gapped OHL from close so a stray NaN never blanks a price row.
        for col in _PRICE_COLS:
            if col not in df.columns:
                df[col] = df["close"]
            df[col] = df[col].fillna(df["close"])
        if "value" not in df.columns:
            df["value"] = df["close"] * df["volume"]

        # Per-ticker frames indexed by date, sorted — the shape every method wants.
        self._by_ticker: dict[str, pd.DataFrame] = {}
        self._span: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {}
        for ticker, g in df.sort_values("date").groupby("ticker", sort=False):
            frame = g.set_index("date")[list(OHLCV_COLUMNS)]
            frame.index.name = "date"
            self._by_ticker[ticker] = frame
            self._span[ticker] = (frame.index.min(), frame.index.max())

    # --- constructors ------------------------------------------------------
    @classmethod
    def from_csv(cls, path: str | Path, **kwargs) -> "CsvDataSource":
        return cls(pd.read_csv(path), **kwargs)

    @property
    def tickers(self) -> list[str]:
        return list(self._by_ticker)

    # --- listing / metadata ------------------------------------------------
    def get_ticker_list(self, on: date, market: Market) -> list[str]:
        """Tickers whose listing span contains ``on`` (point-in-time).

        A ticker delisted before ``on`` or first listed after it is absent, so
        the reconstructed universe is survivorship-bias-free by construction.
        """
        if market != self.market:
            return []
        stamp = pd.Timestamp(as_date(on))
        return [t for t, (lo, hi) in self._span.items() if lo <= stamp <= hi]

    def get_etf_etn_ticker_list(self, on: date) -> list[str]:
        return list(self._etf_etn)

    def get_ticker_name(self, ticker: str, on: date | None = None) -> str:
        return self._names.get(ticker, ticker)

    def get_market_cap(self, on: date, market: Market) -> pd.DataFrame:
        """Trailing dollar-volume proxy as of ``on`` (see module caveats)."""
        if market != self.market:
            empty = pd.DataFrame({"mktcap": {}})
            empty.index.name = "ticker"
            return empty
        stamp = pd.Timestamp(as_date(on))
        proxy: dict[str, float] = {}
        for ticker, frame in self._by_ticker.items():
            hist = frame.loc[:stamp, "value"].tail(self._mktcap_lookback)
            if len(hist):
                proxy[ticker] = float(hist.median())
        df = pd.DataFrame({"mktcap": proxy})
        df.index.name = "ticker"
        return df

    # --- prices ------------------------------------------------------------
    def get_ohlcv(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        frame = self._by_ticker[ticker]
        return frame.loc[str(as_date(start)) : str(as_date(end))].copy()

    def get_adjusted_close(self, ticker: str, start: date, end: date) -> pd.Series:
        # No separate adjustment series in a price-only CSV — close is the truth.
        return self.get_ohlcv(ticker, start, end)["close"]
