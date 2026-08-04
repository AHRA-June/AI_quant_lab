"""In-memory :class:`DataSource` for network-free tests.

Models a tiny KRX slice with one of each instrument type (common / preferred /
SPAC / REIT / ETF) plus a 2:1 split on the common name so the adjustment factor
is non-trivial.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from quantlab.data.source import DataSource
from quantlab.types import Market

# ticker -> (name, market, mktcap)
_SECURITIES = {
    "005930": ("삼성전자", Market.KOSPI, 400_000_000),  # common
    "005935": ("삼성전자우", Market.KOSPI, 50_000_000),  # preferred (suffix 5 + name 우)
    "000660": ("SK하이닉스", Market.KOSPI, 120_000_000),  # common
    "349070": ("유안타제12호스팩", Market.KOSDAQ, 3_000_000),  # SPAC
    "330590": ("롯데리츠", Market.KOSPI, 8_000_000),  # REIT
    "069500": ("KODEX 200", Market.KOSPI, 60_000_000),  # ETF
}

_ETF = {"069500"}


class FakeDataSource(DataSource):
    def __init__(self) -> None:
        self._dates = pd.bdate_range("2024-01-01", "2024-03-29")

    # --- listing / metadata ------------------------------------------------
    def get_ticker_list(self, on: date, market: Market) -> list[str]:
        return [t for t, (_, m, _) in _SECURITIES.items() if m == market]

    def get_etf_etn_ticker_list(self, on: date) -> list[str]:
        return list(_ETF)

    def get_ticker_name(self, ticker: str, on: date | None = None) -> str:
        return _SECURITIES[ticker][0]

    def get_market_cap(self, on: date, market: Market) -> pd.DataFrame:
        rows = {t: cap for t, (_, m, cap) in _SECURITIES.items() if m == market}
        df = pd.DataFrame({"mktcap": rows})
        df.index.name = "ticker"
        return df

    # --- prices ------------------------------------------------------------
    def _raw_frame(self, ticker: str) -> pd.DataFrame:
        n = len(self._dates)
        # Deterministic price path; common name '005930' gets a 2:1 split mid-series.
        base = 100.0 + pd.Series(range(n), index=self._dates, dtype=float)
        close = base.copy()
        volume = pd.Series(1_000_000, index=self._dates, dtype=float)
        if ticker == "005930":
            split_at = n // 2
            close.iloc[split_at:] = close.iloc[split_at:] / 2.0
            volume.iloc[split_at:] = volume.iloc[split_at:] * 2.0
        df = pd.DataFrame(
            {
                "open": close,
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": volume,
                "value": close * volume,
            }
        )
        df.index.name = "date"
        return df

    def get_ohlcv(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        df = self._raw_frame(ticker)
        return df.loc[str(start) : str(end)]

    def get_adjusted_close(self, ticker: str, start: date, end: date) -> pd.Series:
        df = self._raw_frame(ticker)
        close = df["close"].copy()
        if ticker == "005930":
            # Back-adjust pre-split prices by the 0.5 split ratio.
            split_at = len(close) // 2
            close.iloc[:split_at] = close.iloc[:split_at] / 2.0
        return close.loc[str(start) : str(end)]
