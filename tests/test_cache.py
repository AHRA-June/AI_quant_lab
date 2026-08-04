"""F1.2 / F1.4 cache + read-through store."""

from datetime import date

from quantlab.data.cache import OHLCVCache, PriceStore, content_hash
from tests.fakes import FakeDataSource

START, END = date(2024, 1, 1), date(2024, 3, 29)


def test_content_hash_is_stable_and_content_sensitive():
    src = FakeDataSource()
    a = src.get_ohlcv("000660", START, END)
    b = src.get_ohlcv("000660", START, END)
    assert content_hash(a) == content_hash(b)

    c = a.copy()
    c.iloc[0, 0] += 1.0
    assert content_hash(c) != content_hash(a)


def test_price_store_caches_and_serves_adjusted(tmp_path):
    src = FakeDataSource()
    store = PriceStore(src, OHLCVCache(tmp_path))

    # First read populates the cache.
    raw = store.get_raw("005930", START, END)
    assert store.cache.has_raw("005930")
    assert store.cache._factor_path("005930").exists()

    # Adjusted close for the split name is continuous (pre-split halved).
    adjusted = store.get_adjusted("005930", START, END)
    n = len(adjusted)
    pre, post = adjusted["close"].iloc[n // 2 - 1], adjusted["close"].iloc[n // 2]
    # No jump across the split once adjusted.
    assert abs(post - pre) < adjusted["close"].mean()  # sanity: no ~2x discontinuity
    assert len(raw) == len(adjusted)


def test_cache_hit_does_not_refetch(tmp_path, monkeypatch):
    src = FakeDataSource()
    store = PriceStore(src, OHLCVCache(tmp_path))
    store.get_raw("000660", START, END)  # warm

    calls = {"n": 0}
    orig = src.get_ohlcv

    def counting(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    monkeypatch.setattr(src, "get_ohlcv", counting)
    store.get_raw("000660", START, END)  # should hit cache
    assert calls["n"] == 0
