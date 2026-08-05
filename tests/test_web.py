"""Web dashboard (M5): store, service, and API — all network-free (synthetic data)."""

import numpy as np
import pandas as pd
import pytest

from quantlab.web.service import (
    available_strategies,
    run_csv_backtest,
    run_synthetic_backtest,
)
from quantlab.web.store import RunRecord, RunStore


def _write_long_csv(path, n_tickers=30, n_days=700, seed=0):
    """A long-format OHLCV CSV with enough history for warm-up + universe build."""
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


_CSV_CFG = (
    'alpha: "rank(returns(close, 20))"\n'
    "universe: {market: [KOSPI], top_mktcap: 20, min_turnover: 0}\n"
    "portfolio: {n_positions: 10, weighting: equal, rebalance: monthly}\n"
)

fastapi = pytest.importorskip("fastapi")  # skip cleanly if the web extra is absent
from fastapi.testclient import TestClient  # noqa: E402

from quantlab.web.app import create_app  # noqa: E402

STRAT = "short_term_reversal"  # fast, no volume needed


# --- store -----------------------------------------------------------------


def test_store_append_and_list_newest_first(tmp_path):
    store = RunStore(tmp_path)
    assert store.list() == []
    for i in range(3):
        store.append(RunRecord(
            id=f"r{i}", created_at=f"2026-01-0{i}T00:00:00", strategy="s", source="synthetic",
            n_positions=10, cagr=0.1, sharpe=1.0, max_drawdown=-0.05, total_return=0.2,
            shuffle_p=0.01, survives=True, trials_logged=i + 1, report_file="report.html",
        ))
    ids = [r.id for r in store.list()]
    assert ids == ["r2", "r1", "r0"]              # newest first
    assert store.get("r1").trials_logged == 2


# --- service ---------------------------------------------------------------


def test_run_synthetic_backtest_persists_record_and_report(tmp_path):
    store = RunStore(tmp_path)
    rec = run_synthetic_backtest(store, strategy=STRAT, n_positions=15, n_shuffles=10)
    assert rec.strategy == STRAT and rec.n_positions == 15
    assert rec.trials_logged >= 1
    # report written and locatable
    path = store.report_path(rec.id)
    assert path is not None and path.exists()
    assert "AI Quant Lab" in path.read_text(encoding="utf-8")
    # persisted to the index
    assert store.get(rec.id) is not None


def test_run_synthetic_backtest_rejects_unknown_strategy(tmp_path):
    with pytest.raises(ValueError):
        run_synthetic_backtest(RunStore(tmp_path), strategy="nope", n_shuffles=5)


def test_run_csv_backtest_real_data_path(tmp_path):
    from datetime import date

    store = RunStore(tmp_path)
    csv = _write_long_csv(tmp_path / "prices.csv")
    rec = run_csv_backtest(
        store, csv_path=csv, config_yaml=_CSV_CFG,
        start=date(2022, 6, 1), end=date(2023, 6, 1), n_shuffles=8,
    )
    assert rec.source == "csv"
    assert rec.universe_size == 20 and rec.window == "2022-06-01→2023-06-01"
    assert store.report_path(rec.id).exists()
    assert store.get(rec.id).universe_size == 20   # round-trips through the index


# --- API -------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(tmp_path, n_shuffles=10))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_dashboard_renders_and_lists_strategies(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "대시보드" in r.text
    assert available_strategies()[0] in r.text  # strategy options present


def test_create_run_json_then_appears_in_list_and_report_served(client):
    resp = client.post("/api/runs", json={"strategy": STRAT, "n_positions": 12})
    assert resp.status_code == 201
    rec = resp.json()
    assert rec["strategy"] == STRAT

    listed = client.get("/api/runs").json()
    assert any(x["id"] == rec["id"] for x in listed)

    report = client.get(f"/runs/{rec['id']}/report")
    assert report.status_code == 200 and "연구 무결성 검증" in report.text


def test_create_run_form_post_redirects_to_dashboard(client):
    resp = client.post(
        "/api/runs", data={"strategy": STRAT, "n_positions": "10"},
        follow_redirects=False,
    )
    assert resp.status_code == 303 and resp.headers["location"] == "/"


def test_unknown_strategy_returns_422(client):
    assert client.post("/api/runs", json={"strategy": "bogus"}).status_code == 422


def test_csv_upload_form_runs_and_appears(client, tmp_path):
    from datetime import date

    csv = _write_long_csv(tmp_path / "up.csv")
    with csv.open("rb") as fh:
        resp = client.post(
            "/api/runs",
            data={"source": "csv", "config_yaml": _CSV_CFG,
                  "start": "2022-06-01", "end": "2023-06-01"},
            files={"csv": ("up.csv", fh, "text/csv")},
            follow_redirects=False,
        )
    assert resp.status_code == 303
    runs = client.get("/api/runs").json()
    assert any(r["source"] == "csv" and r["universe_size"] == 20 for r in runs)


def test_csv_without_file_returns_422(client):
    resp = client.post(
        "/api/runs",
        data={"source": "csv", "start": "2022-06-01", "end": "2023-06-01"},
        follow_redirects=False,
    )
    assert resp.status_code == 422


def test_missing_report_404(client):
    assert client.get("/runs/does-not-exist/report").status_code == 404
