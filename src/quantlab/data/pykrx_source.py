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


def _asof_trading_day(stock, on: date) -> str:
    """Snap an *as-of* date to the nearest **trading** day.

    KRX is closed on weekends and holidays (e.g. 2025-05-01 근로자의 날). pykrx's
    snapshot calls (``get_market_cap``/``get_market_ticker_list``) return an empty
    frame for a closed day and then raise a cryptic ``KeyError`` on the Korean
    columns. Resolving to the nearest prior session first makes point-in-time
    universe building robust to holidays.
    """
    d = to_krx_datestr(on)
    fn = getattr(stock, "get_nearest_business_day_in_a_week", None)
    if fn is None:  # pragma: no cover - depends on pykrx version
        return d
    try:
        return fn(date=d, prev=True)          # snap backward (point-in-time safe)
    except TypeError:                          # older pykrx: no ``prev`` kwarg
        try:
            return fn(d)
        except Exception:                      # noqa: BLE001 - vendor call, tolerate
            return d
    except Exception:                          # noqa: BLE001
        return d


def _is_network_error(exc: BaseException) -> bool:
    """True if ``exc`` (or something in its cause chain) is a connectivity failure
    — a dead network/proxy/TLS/timeout, not a "KRX has no data for this date"."""
    seen = 0
    e: BaseException | None = exc
    while e is not None and seen < 8:
        mod = (type(e).__module__ or "").lower()
        name = type(e).__name__.lower()
        if ("requests" in mod or "urllib3" in mod or "socket" in mod
                or any(k in name for k in ("connection", "proxy", "timeout", "ssl"))):
            return True
        e = e.__cause__ or e.__context__
        seen += 1
    return False


def _asof_candidates(stock, on: date, max_back: int = 7):
    """Ordered YYYYMMDD strings to try for an *as-of* snapshot: the snapped
    trading day first, then each of the previous ``max_back`` calendar days.

    Deduplicated, order-preserving. Covers holidays/weekends (via the snap) *and*
    a just-closed session whose snapshot KRX hasn't published yet (via walk-back).
    """
    from datetime import timedelta

    cands = [_asof_trading_day(stock, on)]
    cands += [to_krx_datestr(on - timedelta(days=k)) for k in range(0, max_back + 1)]
    seen: set[str] = set()
    out: list[str] = []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


class PykrxDataSource(DataSource):
    """Live KRX data via pykrx."""

    def get_ticker_list(self, on: date, market: Market) -> list[str]:
        stock = _require_pykrx()
        return list(stock.get_market_ticker_list(_asof_trading_day(stock, on), market=market.value))

    def get_etf_etn_ticker_list(self, on: date) -> list[str]:
        stock = _require_pykrx()
        d = _asof_trading_day(stock, on)
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
        fromdate, todate = to_krx_datestr(start), to_krx_datestr(end)
        df = self._normalize_ohlcv(
            stock.get_market_ohlcv(fromdate, todate, ticker, adjusted=False))
        if df.empty:
            # The raw (adjusted=False) feed is served by KRX's MDCSTAT endpoint,
            # which is unavailable in some environments, while adjusted prices
            # (Naver-backed) still work. Fall back to those — adjusted prices are
            # what the backtest wants anyway, and the factor then collapses to 1.
            alt = self._normalize_ohlcv(
                stock.get_market_ohlcv(fromdate, todate, ticker, adjusted=True))
            if not alt.empty:
                return alt
        return df

    def get_adjusted_close(self, ticker: str, start: date, end: date) -> pd.Series:
        stock = _require_pykrx()
        df = stock.get_market_ohlcv(
            to_krx_datestr(start), to_krx_datestr(end), ticker, adjusted=True
        )
        df = self._normalize_ohlcv(df)
        return df["close"]

    def get_market_cap(self, on: date, market: Market) -> pd.DataFrame:
        stock = _require_pykrx()
        # pykrx's get_market_cap raises a cryptic KeyError on the Korean columns
        # (['종가','시가총액','거래량','거래대금']) whenever KRX returns nothing for the
        # date — a holiday, a weekend, or a session whose snapshot isn't published
        # yet. Snap to the nearest session, then walk back up to a week trying each
        # candidate so a just-closed/holiday start date still resolves to real data.
        df = None
        last_exc: Exception | None = None
        for cand in _asof_candidates(stock, on):
            try:
                got = stock.get_market_cap(cand, market=market.value)
            except Exception as exc:  # noqa: BLE001 - vendor raises KeyError on empty payloads
                last_exc = exc
                # A dead network/proxy won't heal across candidates — surface it now
                # with a distinct message instead of hammering KRX and then blaming
                # the date.
                if _is_network_error(exc):
                    raise ValueError(
                        "KRX 서버에 접속하지 못했습니다 — 네트워크·프록시·방화벽·백신을 "
                        f"확인하세요. [{type(exc).__name__}]"
                    ) from exc
                continue
            if got is not None and not got.empty:
                df = got
                break
        if df is None:
            hint = (f" [pykrx 마지막 오류: {type(last_exc).__name__}]" if last_exc else "")
            raise ValueError(
                f"KRX에서 {on:%Y-%m-%d} 근처의 시가총액 데이터를 받지 못했습니다 "
                "(휴장일이거나 아직 공개 전인 날짜일 수 있습니다). pykrx를 최신으로 업데이트"
                "(pip install -U pykrx)하거나, 데이터가 확정된 과거 거래일로 시작일을 잡아 보세요."
                f"{hint}"
            )
        # pykrx returns a '시가총액' column indexed by ticker.
        out = pd.DataFrame(index=df.index)
        out.index.name = "ticker"
        out["mktcap"] = df["시가총액"] if "시가총액" in df.columns else df.iloc[:, 0]
        return out

    _CANON = ("open", "high", "low", "close", "volume", "value")

    @classmethod
    def _normalize_ohlcv(cls, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize a pykrx OHLCV frame to canonical columns.

        Robust to two vendor realities: (1) per-ticker OHLCV omits 거래대금, so
        ``value`` is derived as close×volume; (2) a delisted/halted/no-data ticker
        comes back empty — we still return a frame carrying every canonical column
        (empty) so downstream ``df["close"]`` never raises ``KeyError: 'close'``.
        """
        df = df.rename(columns=_OHLCV_RENAME)
        if "value" not in df.columns and {"close", "volume"} <= set(df.columns):
            df = df.assign(value=df["close"] * df["volume"])
        keep = [c for c in cls._CANON if c in df.columns]
        df = df[keep].copy()
        for col in cls._CANON:                      # guarantee all canonical columns
            if col not in df.columns:
                df[col] = pd.Series(dtype="float64")
        df = df[list(cls._CANON)]
        df.index = pd.to_datetime(df.index)
        df.index.name = "date"
        return df
