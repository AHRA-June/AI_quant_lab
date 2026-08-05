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
import json
from datetime import date
from pathlib import Path

import pandas as pd

from quantlab.types import as_date

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
        self._meta = self.root / "meta"
        self._ohlcv.mkdir(parents=True, exist_ok=True)
        self._factor.mkdir(parents=True, exist_ok=True)
        self._meta.mkdir(parents=True, exist_ok=True)

    def _ohlcv_path(self, ticker: str) -> Path:
        return self._ohlcv / f"{ticker}.parquet"

    def _factor_path(self, ticker: str) -> Path:
        return self._factor / f"{ticker}.parquet"

    def _meta_path(self, ticker: str) -> Path:
        return self._meta / f"{ticker}.json"

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

    # --- coverage tracking -------------------------------------------------
    # Coverage records the [start, end] *requested* range a ticker's cache was
    # filled over — not the range of data that came back. Keying off the request
    # keeps a late-listed ticker (whose data starts after ``start``) from being
    # refetched forever, while still letting a wider later request grow the cache.
    def covered(self, ticker: str) -> tuple[date, date] | None:
        path = self._meta_path(ticker)
        if not path.exists():
            return None
        meta = json.loads(path.read_text(encoding="utf-8"))
        return as_date(meta["start"]), as_date(meta["end"])

    def set_covered(self, ticker: str, start: date, end: date) -> None:
        self._meta_path(ticker).write_text(
            json.dumps({"start": as_date(start).isoformat(), "end": as_date(end).isoformat()}),
            encoding="utf-8",
        )


class PriceStore:
    """Read-through price access: source → cache → adjusted reads."""

    def __init__(self, source: DataSource, cache: OHLCVCache) -> None:
        self.source = source
        self.cache = cache

    def _ensure_cached(self, ticker: str, start: date, end: date) -> None:
        start, end = as_date(start), as_date(end)
        covered = self.cache.covered(ticker) if self.cache.has_raw(ticker) else None
        if covered is not None:
            cov_start, cov_end = covered
            if cov_start <= start and cov_end >= end:
                return  # request already inside cached coverage
            # widen to the union so a later, larger window never truncates the cache
            start, end = min(start, cov_start), max(end, cov_end)
        raw = self.source.get_ohlcv(ticker, start, end)
        adj_close = self.source.get_adjusted_close(ticker, start, end)
        factor = derive_factor(raw["close"], adj_close)
        self.cache.put_raw(ticker, raw)
        self.cache.put_factor(ticker, factor)
        self.cache.set_covered(ticker, start, end)

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
