"""Paper trading (페이퍼 트레이딩) — store, service, and API. All network-free:
screens run on RichFakeDataSource / an in-memory CSV, and marking uses an injected
fake source or the pinned CSV. No pykrx, no network."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from quantlab.web.paper import (
    DEFAULT_NOTIONAL,
    PaperStore,
    mark_paper,
    open_from_screen,
)
from quantlab.web.service import read_screen, run_screen
from quantlab.web.store import RunStore
from tests.fakes import RichFakeDataSource

_CFG = (
    'alpha: "close"\n'
    "universe: {market: [KOSPI], top_mktcap: 20, min_turnover: 0}\n"
    "portfolio: {n_positions: 5, weighting: equal, rebalance: weekly}\n"
)
_EXPR = "close > ts_mean(close, 20)"


def _write_long_csv(path, n_tickers=30, n_days=700, seed=0):
    idx = pd.bdate_range("2021-01-01", periods=n_days)
    rng = np.random.default_rng(seed)
    frames = []
    for i in range(n_tickers):
        close = 100 * np.cumprod(1 + rng.normal(0.0004, 0.02, n_days))
        vol = rng.lognormal(12, 0.5, n_days)
        frames.append(pd.DataFrame({
            "date": idx, "open": close, "high": close, "low": close,
            "close": close, "volume": vol, "Name": f"S{i:02d}",
        }))
    pd.concat(frames, ignore_index=True).to_csv(path, index=False)
    return path


def _make_krx_screen(tmp_path, source=None):
    """A screen run over the fake KRX source (kind='krx' → no CSV pin needed)."""
    store = RunStore(tmp_path)
    rec = run_screen(
        store, source=source or RichFakeDataSource(), config_yaml=_CFG,
        start=date(2021, 7, 1), end=date(2022, 12, 31), screen_expr=_EXPR,
        n_shuffles=6, kind="krx",
    )
    return store, rec


# --- open_from_screen ------------------------------------------------------


def test_open_from_screen_sizes_equal_weight_book(tmp_path):
    store, rec = _make_krx_screen(tmp_path)
    paper = PaperStore(store.base)
    snap = read_screen(store, rec.id)

    p = open_from_screen(store, paper, rec.id, kind="krx", notional=10_000_000)

    assert p.kind == "krx" and p.origin_run_id == rec.id
    assert p.n_holdings == len(snap["matches"]) >= 1
    # equal weight, sums to ~1
    assert abs(sum(h.weight for h in p.holdings) - 1.0) < 1e-9
    assert all(abs(h.weight - 1.0 / p.n_holdings) < 1e-12 for h in p.holdings)
    # fully invested: entry value == notional (fractional shares)
    assert abs(p.market_value - p.notional) < 1.0
    # shares sized from entry price
    for h in p.holdings:
        assert h.shares == pytest.approx(p.notional * h.weight / h.entry_price)
    # unmarked → no P&L yet
    assert p.marked_at is None and p.pnl_pct is None
    # persisted and retrievable
    assert paper.get(p.id).n_holdings == p.n_holdings


def test_open_from_screen_defaults_notional(tmp_path):
    store, rec = _make_krx_screen(tmp_path)
    paper = PaperStore(store.base)
    p = open_from_screen(store, paper, rec.id, kind="krx")
    assert p.notional == DEFAULT_NOTIONAL


def test_open_from_screen_missing_run_raises(tmp_path):
    store = RunStore(tmp_path)
    paper = PaperStore(store.base)
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        open_from_screen(store, paper, "nope", kind="krx")


def test_open_from_screen_csv_requires_pinnable_file(tmp_path):
    store, rec = _make_krx_screen(tmp_path)
    paper = PaperStore(store.base)
    with pytest.raises(ValueError, match="CSV 원본"):
        open_from_screen(store, paper, rec.id, kind="csv", csv_path=None)


# --- mark_paper ------------------------------------------------------------


def test_mark_paper_with_injected_source_computes_pnl(tmp_path):
    src = RichFakeDataSource()
    store, rec = _make_krx_screen(tmp_path, source=src)
    paper = PaperStore(store.base)
    p = open_from_screen(store, paper, rec.id, kind="krx")

    marked = mark_paper(paper, p.id, source=src, mark_date=date(2022, 12, 31))

    assert marked.marked_at and marked.mark_date == "2022-12-31"
    assert marked.pnl_pct is not None
    assert all(h.priced and h.last_price is not None for h in marked.holdings)
    # market value equals sum shares * last price
    expect = sum(h.shares * h.last_price for h in marked.holdings)
    assert marked.market_value == pytest.approx(expect)
    # verdict round-trips through disk
    assert paper.get(p.id).pnl_pct == pytest.approx(marked.pnl_pct)


def test_mark_paper_skips_ticker_with_no_data(tmp_path):
    src = RichFakeDataSource()
    store, rec = _make_krx_screen(tmp_path, source=src)
    paper = PaperStore(store.base)
    p = open_from_screen(store, paper, rec.id, kind="krx")
    dead = p.holdings[0].ticker

    class _Partial(RichFakeDataSource):
        def get_adjusted_close(self, ticker, start, end):
            if ticker == dead:
                return pd.Series(dtype="float64", name="close")   # no data
            return super().get_adjusted_close(ticker, start, end)

    marked = mark_paper(paper, p.id, source=_Partial(), mark_date=date(2022, 12, 31))
    dead_h = next(h for h in marked.holdings if h.ticker == dead)
    assert dead_h.priced is False and dead_h.last_price is None
    assert dead_h.market_value == pytest.approx(dead_h.entry_value)   # held flat
    assert marked.marked_at is not None                              # still marked overall


def test_mark_paper_rejects_mark_before_entry(tmp_path):
    src = RichFakeDataSource()
    store, rec = _make_krx_screen(tmp_path, source=src)
    paper = PaperStore(store.base)
    p = open_from_screen(store, paper, rec.id, kind="krx")
    with pytest.raises(ValueError, match="앞설 수 없습니다"):
        mark_paper(paper, p.id, source=src, mark_date=date(2000, 1, 1))


def test_csv_portfolio_pins_data_and_marks_offline(tmp_path):
    """A CSV-origin book copies the source CSV (pin) and re-marks with no external
    file — the offline-reproducible path."""
    from quantlab.data.csv_source import CsvDataSource
    from quantlab.web.paper import PIN_DIR

    csv = _write_long_csv(tmp_path / "prices.csv")
    store = RunStore(tmp_path)
    rec = run_screen(
        store, source=CsvDataSource.from_csv(csv), config_yaml=_CFG,
        start=date(2022, 6, 1), end=date(2023, 6, 1), screen_expr=_EXPR,
        n_shuffles=6, kind="csv", data_ref="prices.csv",
    )
    paper = PaperStore(store.base)
    p = open_from_screen(store, paper, rec.id, kind="csv", csv_path=csv)
    assert p.data_ref == "prices.csv"
    pinned = paper.root / p.id / PIN_DIR / "prices.csv"
    assert pinned.exists()

    # delete the original CSV → marking still works from the pin (source=None)
    csv.unlink()
    marked = mark_paper(paper, p.id, mark_date=date(2023, 6, 1))
    assert marked.marked_at and all(h.priced for h in marked.holdings)


# --- PaperStore ------------------------------------------------------------


def test_paper_store_list_newest_first_and_delete(tmp_path):
    store, rec = _make_krx_screen(tmp_path)
    paper = PaperStore(store.base)
    p1 = open_from_screen(store, paper, rec.id, kind="krx", name="A")
    p2 = open_from_screen(store, paper, rec.id, kind="krx", name="B")
    ids = [p.id for p in paper.list()]
    assert set(ids) == {p1.id, p2.id} and len(ids) == 2
    assert paper.delete(p1.id) is True
    assert paper.get(p1.id) is None
    assert [p.id for p in paper.list()] == [p2.id]
    assert paper.delete("nope") is False


# --- API -------------------------------------------------------------------

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from quantlab.web.app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(tmp_path, n_shuffles=8, llm_client=None))


def _wait_runs(client, n, timeout=25):
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        runs = client.get("/api/runs").json()
        if len(runs) >= n:
            return runs
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {n} run(s)")


def _make_csv_screen_via_api(client, tmp_path):
    csv = _write_long_csv(tmp_path / "s.csv")
    with csv.open("rb") as fh:
        client.post(
            "/api/screen",
            data={"source": "csv", "start": "2022-06-01", "end": "2023-06-01",
                  "screen_expr": _EXPR, "config_yaml": _CFG},
            files={"csv": ("s.csv", fh, "text/csv")}, follow_redirects=False,
        )
    return _wait_runs(client, 1)[0]["id"]


def test_paper_tab_present_and_empty(client):
    r = client.get("/paper")
    assert r.status_code == 200
    assert "종이 포트폴리오" in r.text and "아직 종이 포트폴리오가 없습니다" in r.text
    assert "종이 포트폴리오" in client.get("/").text          # nav link on dashboard


def test_paper_full_flow_create_mark_delete(client, tmp_path):
    rid = _make_csv_screen_via_api(client, tmp_path)

    # screen result page offers the "담기" button
    assert "종이 포트폴리오로 담기" in client.get(f"/screen/{rid}").text

    # create from the screen
    resp = client.post("/api/paper", data={"run_id": rid}, follow_redirects=False)
    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert loc.startswith("/paper/")
    pid = loc.split("/paper/")[1]

    detail = client.get(f"/paper/{pid}")
    assert detail.status_code == 200 and "보유 종목" in detail.text

    # it shows up in the list
    assert pid in client.get("/paper").text

    # mark to market (pinned CSV → offline)
    m = client.post(f"/paper/{pid}/mark", data={"mark_date": "2023-06-01"},
                    follow_redirects=False)
    assert m.status_code == 303
    marked = client.get(f"/paper/{pid}").text
    assert "평가금액" in marked and "최근 평가" in marked

    # delete
    d = client.post(f"/paper/{pid}/delete", follow_redirects=False)
    assert d.status_code == 303
    assert client.get(f"/paper/{pid}").status_code == 404


def test_paper_create_unknown_run_404(client):
    assert client.post("/api/paper", data={"run_id": "nope"}).status_code == 404


def test_paper_mark_missing_portfolio_404(client):
    assert client.post("/paper/nope/mark", data={}).status_code == 404
