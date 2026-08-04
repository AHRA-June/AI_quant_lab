"""Local price cache + read-through reader (F1.2, F1.4).

Layout under ``cache_dir``::

    ohlcv/<ticker>.parquet    raw (unadjusted) OHLCV
    factor/<ticker>.parquet   adjustment factor series (DQ.1)

``PriceStore`` wraps a :class:`~quantlab.data.source.DataSource`: it fetches raw
OHLCV + derives the adjustment factor on a miss, persists both, and serves
**adjusted** prices computed at read time. Callers never see a pre-adjusted
snapshot on disk.

Reproducibility (F1.4): :func:`content_hash` yields a stable digest of a frame,
the building block of the experiment reproducibility bundle
(``hash(artifact + data snapshot + engine SHA + seed)``).
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pandas as pd

from quantlab.data.adjust import apply_adjustment, derive_factor
from quantlab.data.source import DataSource


def content_hash(obj: pd.DataFrame | pd.Series) -> str:
    """Deterministic SHA-256 (first 16 hex chars) of a DataFrame/Series."""
    # pandas' hash_pandas_object is stable across runs for equal content.
    row_hashes = pd.util.hash_pandas_object(obj, index=True).values
    digest = hashlib.sha256(row_hashes.tobytes())
    digest.update(str(list(getattr(obj, "columns", []))).encode())
    return digest.hexdigest()[:16]


class OHLCVCache:
    """Thin parquet-backed store for raw OHLCV and adjustment factors."""

    def __init__(self, cache_dir: str | Path) -> None:
        self.root = Path(cache_dir)
        self._ohlcv = self.root / "ohlcv"
        self._factor = self.root / "factor"
        self._ohlcv.mkdir(parents=True, exist_ok=True)
        self._factor.mkdir(parents=True, exist_ok=True)

    def _ohlcv_path(self, ticker: str) -> Path:
        return self._ohlcv / f"{ticker}.parquet"

    def _factor_path(self, ticker: str) -> Path:
        return self._factor / f"{ticker}.parquet"

    def has_raw(self, ticker: str) -> bool:
        return self._ohlcv_path(ticker).exists()

    def put_raw(self, ticker: str, ohlcv: pd.DataFrame) -> None:
        ohlcv.to_parquet(self._ohlcv_path(ticker))

    def get_raw(self, ticker: str) -> pd.DataFrame:
        return pd.read_parquet(self._ohlcv_path(ticker))

    def put_factor(self, ticker: str, factor: pd.Series) -> None:
        factor.to_frame("factor").to_parquet(self._factor_path(ticker))

    def get_factor(self, ticker: str) -> pd.Series:
        return pd.read_parquet(self._factor_path(ticker))["factor"]


class PriceStore:
    """Read-through price access: source → cache → adjusted reads."""

    def __init__(self, source: DataSource, cache: OHLCVCache) -> None:
        self.source = source
        self.cache = cache

    def _ensure_cached(self, ticker: str, start: date, end: date) -> None:
        if self.cache.has_raw(ticker):
            return
        raw = self.source.get_ohlcv(ticker, start, end)
        adj_close = self.source.get_adjusted_close(ticker, start, end)
        factor = derive_factor(raw["close"], adj_close)
        self.cache.put_raw(ticker, raw)
        self.cache.put_factor(ticker, factor)

    def get_raw(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        self._ensure_cached(ticker, start, end)
        raw = self.cache.get_raw(ticker)
        return raw.loc[str(start) : str(end)]

    def get_adjusted(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """Adjusted OHLCV computed at read time from raw + factor (DQ.1)."""
        self._ensure_cached(ticker, start, end)
        raw = self.cache.get_raw(ticker)
        factor = self.cache.get_factor(ticker)
        adjusted = apply_adjustment(raw, factor)
        return adjusted.loc[str(start) : str(end)]
