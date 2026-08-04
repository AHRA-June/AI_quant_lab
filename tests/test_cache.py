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


def test_widening_the_window_refetches_and_serves_full_range(tmp_path):
    """A first narrow read must not pin the cache: a later wider read has to
    grow it, or downstream panels get silently truncated (the run_backtest
    universe→panel ordering trap)."""
    src = FakeDataSource()
    store = PriceStore(src, OHLCVCache(tmp_path))

    narrow_end = date(2024, 1, 31)
    store.get_raw("000660", START, narrow_end)  # warm with a short window
    assert store.get_raw("000660", START, narrow_end).index.max().date() <= narrow_end

    wide = store.get_raw("000660", START, END)  # ask for the full range
    assert wide.index.max().date() > narrow_end  # cache grew, not truncated
    assert wide.index.max().date() >= date(2024, 3, 28)


def test_narrower_read_after_wide_still_cache_hits(tmp_path, monkeypatch):
    src = FakeDataSource()
    store = PriceStore(src, OHLCVCache(tmp_path))
    store.get_raw("000660", START, END)  # warm wide

    calls = {"n": 0}
    orig = src.get_ohlcv
    monkeypatch.setattr(
        src, "get_ohlcv", lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), orig(*a, **k))[1]
    )
    store.get_raw("000660", date(2024, 2, 1), date(2024, 2, 15))  # inside coverage
    assert calls["n"] == 0
