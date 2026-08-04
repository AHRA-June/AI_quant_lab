"""§11 point-in-time universe reconstruction."""

from datetime import date

from quantlab.data.cache import OHLCVCache, PriceStore
from quantlab.data.universe import UniverseBuilder
from quantlab.types import Market, UniverseSpec
from tests.fakes import FakeDataSource

ON = date(2024, 3, 15)


def test_universe_excludes_special_types_and_ranks_by_mktcap():
    builder = UniverseBuilder(FakeDataSource())  # no price store -> skip liquidity
    tickers = builder.build(ON, UniverseSpec(top_mktcap=10))
    # Only the two common stocks survive (preferred/spac/reit/etf dropped).
    assert set(tickers) == {"005930", "000660"}
    # Ranked by market cap: 삼성전자(400M) before SK하이닉스(120M).
    assert tickers == ["005930", "000660"]


def test_top_n_truncates():
    builder = UniverseBuilder(FakeDataSource())
    tickers = builder.build(ON, UniverseSpec(top_mktcap=1))
    assert tickers == ["005930"]


def test_kospi_only_scope():
    builder = UniverseBuilder(FakeDataSource())
    spec = UniverseSpec(markets=(Market.KOSPI,), top_mktcap=10)
    tickers = builder.build(ON, spec)
    assert "005930" in tickers and "000660" in tickers


def test_liquidity_filter_applied_with_price_store(tmp_path):
    src = FakeDataSource()
    store = PriceStore(src, OHLCVCache(tmp_path))
    builder = UniverseBuilder(src, price_store=store)
    # FakeDataSource 20d-median turnover ~1.5e8. A 1e8 floor keeps both commons...
    kept = builder.build(ON, UniverseSpec(top_mktcap=10, min_turnover=1e8))
    assert set(kept) == {"005930", "000660"}
    # ...while a 1e9 floor removes everything (filter is actually applied).
    dropped = builder.build(ON, UniverseSpec(top_mktcap=10, min_turnover=1e9))
    assert dropped == []
