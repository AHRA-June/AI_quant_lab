"""CsvDataSource — long-format CSV fed through the DataSource contract."""

from datetime import date
from io import StringIO

import pandas as pd
import pytest

from quantlab.data.cache import OHLCVCache, PriceStore
from quantlab.data.csv_source import CsvDataSource
from quantlab.data.panels import adjusted_panels
from quantlab.types import Market, OHLCV_COLUMNS

# AAA lists across the whole window; BBB lists late (delisting/late-listing test).
CSV = """date,open,high,low,close,volume,Name
2024-01-02,10,10.5,9.8,10.0,1000,AAA
2024-01-03,10,10.5,9.8,11.0,1200,AAA
2024-01-04,11,11.5,10.8,12.0,1500,AAA
2024-01-05,12,12.5,11.8,13.0,900,AAA
2024-01-04,20,20.5,19.8,20.0,500,BBB
2024-01-05,20,20.5,19.8,21.0,700,BBB
"""


def _source() -> CsvDataSource:
    return CsvDataSource(pd.read_csv(StringIO(CSV)))


def test_pit_listing_excludes_not_yet_listed():
    src = _source()
    # BBB's first row is 2024-01-04, so it is not "listed" on 2024-01-02.
    assert src.get_ticker_list(date(2024, 1, 2), Market.KOSPI) == ["AAA"]
    assert set(src.get_ticker_list(date(2024, 1, 4), Market.KOSPI)) == {"AAA", "BBB"}
    # A market this source does not carry yields nothing.
    assert src.get_ticker_list(date(2024, 1, 4), Market.KOSDAQ) == []


def test_value_column_is_derived():
    src = _source()
    ohlcv = src.get_ohlcv("AAA", date(2024, 1, 2), date(2024, 1, 5))
    assert set(OHLCV_COLUMNS) <= set(ohlcv.columns)
    # value == close * volume on the first row
    assert ohlcv["value"].iloc[0] == pytest.approx(10.0 * 1000)


def test_market_cap_proxy_is_point_in_time():
    src = _source()
    # As of 2024-01-03 only AAA has traded; BBB not yet listed -> absent.
    mc = src.get_market_cap(date(2024, 1, 3), Market.KOSPI)
    assert "mktcap" in mc.columns
    assert "BBB" not in mc.index
    assert mc.loc["AAA", "mktcap"] > 0


def test_adjusted_equals_raw_without_a_factor():
    src = _source()
    raw = src.get_ohlcv("AAA", date(2024, 1, 2), date(2024, 1, 5))["close"]
    adj = src.get_adjusted_close("AAA", date(2024, 1, 2), date(2024, 1, 5))
    pd.testing.assert_series_equal(raw, adj, check_names=False)


def test_flows_through_price_store_and_panels(tmp_path):
    src = _source()
    store = PriceStore(src, OHLCVCache(tmp_path))
    panels = adjusted_panels(store, ["AAA", "BBB"], date(2024, 1, 2), date(2024, 1, 5))
    assert set(panels) == set(OHLCV_COLUMNS)
    close = panels["close"]
    assert list(close.columns) == ["AAA", "BBB"]
    # BBB is NaN before it lists, present after — the panel keeps the gap.
    assert pd.isna(close.loc["2024-01-02", "BBB"])
    assert close.loc["2024-01-05", "BBB"] == 21.0
