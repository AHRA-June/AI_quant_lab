"""PykrxDataSource holiday/edge handling — network-free via a fake ``stock`` module."""

from datetime import date

import pandas as pd
import pytest

from quantlab.data import pykrx_source
from quantlab.data.pykrx_source import PykrxDataSource, _asof_trading_day
from quantlab.types import Market


class _FakeStock:
    """Minimal stand-in for ``pykrx.stock`` — records the date it was queried with."""

    def __init__(self, *, nearest="20250430", cap_by_date=None, has_prev=True,
                 raise_on_missing=False):
        self.nearest = nearest
        self.cap_by_date = cap_by_date or {}
        self.has_prev = has_prev
        self.raise_on_missing = raise_on_missing
        self.asked = None
        self.tried = []

    def get_nearest_business_day_in_a_week(self, date=None, prev=True):  # noqa: A002
        if not self.has_prev and prev is not True:
            raise TypeError("no prev kwarg")
        return self.nearest

    def get_market_cap(self, d, market=None):
        self.asked = d
        self.tried.append(d)
        if d in self.cap_by_date:
            return self.cap_by_date[d]
        if self.raise_on_missing:                       # mimic pykrx's internal KeyError
            raise KeyError("None of Index(['종가','시가총액','거래량','거래대금'])")
        return pd.DataFrame()

    def get_market_ticker_list(self, d, market=None):
        self.asked = d
        return ["005930", "000660"]


def test_asof_snaps_holiday_to_prior_trading_day():
    fake = _FakeStock(nearest="20250430")
    # 2025-05-01 is 근로자의 날 (closed) → snap back to 2025-04-30
    assert _asof_trading_day(fake, date(2025, 5, 1)) == "20250430"


def test_asof_falls_back_when_helper_missing():
    class NoHelper:
        pass
    assert _asof_trading_day(NoHelper(), date(2025, 5, 1)) == "20250501"


def test_get_market_cap_queries_snapped_date(monkeypatch):
    cap = pd.DataFrame({"시가총액": [4e14, 5e13]}, index=["005930", "000660"])
    fake = _FakeStock(nearest="20250430", cap_by_date={"20250430": cap})
    monkeypatch.setattr(pykrx_source, "_require_pykrx", lambda: fake)

    out = PykrxDataSource().get_market_cap(date(2025, 5, 1), Market.KOSPI)
    assert fake.asked == "20250430"                    # snapped, not the holiday
    assert list(out.columns) == ["mktcap"]
    assert out.loc["005930", "mktcap"] == 4e14


def test_get_market_cap_raises_clear_error_on_empty(monkeypatch):
    fake = _FakeStock(nearest="20250430", cap_by_date={})   # empty for every date
    monkeypatch.setattr(pykrx_source, "_require_pykrx", lambda: fake)
    with pytest.raises(ValueError, match="시가총액 데이터를 받지 못했습니다"):
        PykrxDataSource().get_market_cap(date(2025, 5, 1), Market.KOSPI)


def test_get_market_cap_walks_back_past_keyerror_to_a_day_with_data(monkeypatch):
    # nearest-helper points at the holiday (no data → pykrx raises KeyError);
    # a session a few days earlier does have data. The source must walk back to it.
    cap = pd.DataFrame({"시가총액": [1e14]}, index=["005930"])
    fake = _FakeStock(nearest="20260501", cap_by_date={"20260428": cap},
                      raise_on_missing=True)
    monkeypatch.setattr(pykrx_source, "_require_pykrx", lambda: fake)
    out = PykrxDataSource().get_market_cap(date(2026, 5, 1), Market.KOSPI)
    assert out.loc["005930", "mktcap"] == 1e14
    assert "20260501" in fake.tried and fake.tried[-1] == "20260428"


def test_network_error_is_reported_distinctly(monkeypatch):
    import requests

    class _NetStock(_FakeStock):
        def get_market_cap(self, d, market=None):
            self.tried.append(d)
            raise requests.exceptions.ProxyError("tunnel 403")

    fake = _NetStock(nearest="20250701")
    monkeypatch.setattr(pykrx_source, "_require_pykrx", lambda: fake)
    with pytest.raises(ValueError, match="접속하지 못했습니다"):
        PykrxDataSource().get_market_cap(date(2025, 7, 1), Market.KOSPI)
    # bails out on the first candidate — does not hammer KRX with a full walk-back
    assert len(fake.tried) == 1


def test_is_network_error_detects_connection_failures():
    import requests
    assert pykrx_source._is_network_error(requests.exceptions.ConnectionError())
    assert pykrx_source._is_network_error(TimeoutError())
    assert not pykrx_source._is_network_error(KeyError("no columns"))


def test_get_ticker_list_uses_snapped_date(monkeypatch):
    fake = _FakeStock(nearest="20250430")
    monkeypatch.setattr(pykrx_source, "_require_pykrx", lambda: fake)
    tickers = PykrxDataSource().get_ticker_list(date(2025, 5, 1), Market.KOSPI)
    assert fake.asked == "20250430" and tickers == ["005930", "000660"]


def test_normalize_ohlcv_derives_value_when_vendor_omits_it():
    # pykrx per-ticker OHLCV has 시가/고가/저가/종가/거래량/등락률 — no 거래대금.
    idx = pd.to_datetime(["2025-07-01", "2025-07-02"])
    raw = pd.DataFrame(
        {"시가": [100, 101], "고가": [102, 103], "저가": [99, 100],
         "종가": [101, 102], "거래량": [10, 20], "등락률": [0.1, 0.2]},
        index=idx,
    )
    out = PykrxDataSource._normalize_ohlcv(raw)
    assert list(out.columns) == ["open", "high", "low", "close", "volume", "value"]
    assert out["value"].tolist() == [101 * 10, 102 * 20]      # derived close×volume


def test_normalize_ohlcv_empty_frame_keeps_canonical_columns():
    # a delisted/halted/no-data ticker returns empty — must NOT KeyError downstream.
    out = PykrxDataSource._normalize_ohlcv(pd.DataFrame())
    assert list(out.columns) == ["open", "high", "low", "close", "volume", "value"]
    assert len(out) == 0
    assert out["close"].empty          # the property that fixes KeyError: 'close'
