"""PykrxDataSource holiday/edge handling — network-free via a fake ``stock`` module."""

from datetime import date

import pandas as pd
import pytest

from quantlab.data import pykrx_source
from quantlab.data.pykrx_source import PykrxDataSource, _asof_trading_day
from quantlab.types import Market


class _FakeStock:
    """Minimal stand-in for ``pykrx.stock`` — records the date it was queried with."""

    def __init__(self, *, nearest="20250430", cap_by_date=None, has_prev=True):
        self.nearest = nearest
        self.cap_by_date = cap_by_date or {}
        self.has_prev = has_prev
        self.asked = None

    def get_nearest_business_day_in_a_week(self, date=None, prev=True):  # noqa: A002
        if not self.has_prev and prev is not True:
            raise TypeError("no prev kwarg")
        return self.nearest

    def get_market_cap(self, d, market=None):
        self.asked = d
        return self.cap_by_date.get(d, pd.DataFrame())

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


def test_get_ticker_list_uses_snapped_date(monkeypatch):
    fake = _FakeStock(nearest="20250430")
    monkeypatch.setattr(pykrx_source, "_require_pykrx", lambda: fake)
    tickers = PykrxDataSource().get_ticker_list(date(2025, 5, 1), Market.KOSPI)
    assert fake.asked == "20250430" and tickers == ["005930", "000660"]
