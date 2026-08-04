"""pykrx-backed :class:`DataSource` (F1.1).

pykrx returns Korean column names and ``YYYYMMDD`` date strings; this adapter
normalizes them to quantlab's canonical schema. The ``pykrx`` import is lazy so
the package (and the whole test suite) works without it installed — only the
methods that actually hit KRX require it.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

import pandas as pd

from quantlab.data.source import DataSource
from quantlab.types import Market, to_krx_datestr

# pykrx OHLCV columns → canonical.
_OHLCV_RENAME = {
    "시가": "open",
    "고가": "high",
    "저가": "low",
    "종가": "close",
    "거래량": "volume",
    "거래대금": "value",
}


def _require_pykrx():
    try:
        from pykrx import stock  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - env dependent
        raise ImportError(
            "pykrx is required for live KRX data. Install with: pip install '.[data]'"
        ) from exc
    return stock


class PykrxDataSource(DataSource):
    """Live KRX data via pykrx."""

    def get_ticker_list(self, on: date, market: Market) -> list[str]:
        stock = _require_pykrx()
        return list(stock.get_market_ticker_list(to_krx_datestr(on), market=market.value))

    def get_etf_etn_ticker_list(self, on: date) -> list[str]:
        stock = _require_pykrx()
        d = to_krx_datestr(on)
        tickers: list[str] = []
        for fn in ("get_etf_ticker_list", "get_etn_ticker_list"):
            getter = getattr(stock, fn, None)
            if getter is not None:
                try:
                    tickers.extend(list(getter(d)))
                except Exception:  # noqa: BLE001 - vendor call, tolerate gaps
                    pass
        return tickers

    def get_ticker_name(self, ticker: str, on: date | None = None) -> str:
        return self._name(ticker)

    @staticmethod
    @lru_cache(maxsize=8192)
    def _name(ticker: str) -> str:
        stock = _require_pykrx()
        return stock.get_market_ticker_name(ticker)

    def get_ohlcv(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        stock = _require_pykrx()
        df = stock.get_market_ohlcv(
            to_krx_datestr(start), to_krx_datestr(end), ticker, adjusted=False
        )
        return self._normalize_ohlcv(df)

    def get_adjusted_close(self, ticker: str, start: date, end: date) -> pd.Series:
        stock = _require_pykrx()
        df = stock.get_market_ohlcv(
            to_krx_datestr(start), to_krx_datestr(end), ticker, adjusted=True
        )
        df = self._normalize_ohlcv(df)
        return df["close"]

    def get_market_cap(self, on: date, market: Market) -> pd.DataFrame:
        stock = _require_pykrx()
        df = stock.get_market_cap(to_krx_datestr(on), market=market.value)
        # pykrx returns a '시가총액' column indexed by ticker.
        out = pd.DataFrame(index=df.index)
        out.index.name = "ticker"
        out["mktcap"] = df["시가총액"] if "시가총액" in df.columns else df.iloc[:, 0]
        return out

    @staticmethod
    def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
        df = df.rename(columns=_OHLCV_RENAME)
        keep = [c for c in ("open", "high", "low", "close", "volume", "value") if c in df.columns]
        df = df[keep].copy()
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        return df
