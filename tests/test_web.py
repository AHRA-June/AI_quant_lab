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


def _wait_runs(client, n, timeout=25):
    """Poll until at least ``n`` finished runs exist (jobs are async)."""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        runs = client.get("/api/runs").json()
        if len(runs) >= n:
            return runs
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {n} run(s)")


def _wait_jobs_settled(client, timeout=25):
    """Poll until every job is terminal (done/failed)."""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        jobs = client.get("/api/jobs").json()
        if jobs and all(j["status"] in ("done", "failed") for j in jobs):
            return jobs
        time.sleep(0.1)
    raise AssertionError("jobs did not settle")

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


class FakeLLM:
    """Deterministic stand-in for an LLM: proposes a DSL config for a strategy idea,
    and returns Korean commentary for a facts prompt — no network, no key."""

    def complete(self, system: str, user: str) -> str:
        if user.startswith("Strategy idea"):
            return (
                'alpha: "rank(returns(close, 20))"\n'
                "universe: {market: [KOSPI, KOSDAQ], top_mktcap: 300, min_turnover: 5e8}\n"
                "portfolio: {n_positions: 15, weighting: equal, rebalance: weekly}\n"
            )
        return "테스트 해설: 이 전략은 셔플 대조군을 이기지 못해 신뢰하기 어렵습니다."


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(tmp_path, n_shuffles=10, llm_client=None))


@pytest.fixture()
def client_llm(tmp_path):
    return TestClient(create_app(tmp_path, n_shuffles=10, llm_client=FakeLLM()))


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_dashboard_renders_and_lists_strategies(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "대시보드" in r.text
    assert available_strategies()[0] in r.text  # strategy options present


def test_create_run_json_enqueues_then_run_appears_and_report_served(client):
    resp = client.post("/api/runs", json={"strategy": STRAT, "n_positions": 12})
    assert resp.status_code == 202                      # enqueued, not run inline
    assert resp.json()["status"] in ("queued", "running")

    runs = _wait_runs(client, 1)
    rec = runs[0]
    assert rec["strategy"] == STRAT
    report = client.get(f"/runs/{rec['id']}/report")
    assert report.status_code == 200 and "연구 무결성 검증" in report.text


def test_jobs_endpoint_tracks_lifecycle(client):
    resp = client.post("/api/runs", json={"strategy": STRAT, "n_positions": 10})
    job_id = resp.json()["job_id"]
    jobs = _wait_jobs_settled(client)
    job = next(j for j in jobs if j["id"] == job_id)
    assert job["status"] == "done" and job["kind"] == "synthetic"
    assert job["run_id"] and any(r["id"] == job["run_id"] for r in client.get("/api/runs").json())


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
    runs = _wait_runs(client, 1)
    assert any(r["source"] == "csv" and r["universe_size"] == 20 for r in runs)


def test_csv_bad_config_fails_the_job(client, tmp_path):
    csv = _write_long_csv(tmp_path / "up.csv")
    with csv.open("rb") as fh:
        resp = client.post(
            "/api/runs",
            data={"source": "csv", "config_yaml": "this: is: not valid: :::",
                  "start": "2022-06-01", "end": "2023-06-01"},
            files={"csv": ("up.csv", fh, "text/csv")},
            follow_redirects=False,
        )
    assert resp.status_code == 303                       # accepted, fails in the worker
    jobs = _wait_jobs_settled(client)
    assert jobs[0]["status"] == "failed" and jobs[0]["error"]
    assert client.get("/api/runs").json() == []          # no run persisted


def test_csv_without_file_returns_422(client):
    resp = client.post(
        "/api/runs",
        data={"source": "csv", "start": "2022-06-01", "end": "2023-06-01"},
        follow_redirects=False,
    )
    assert resp.status_code == 422


def test_missing_report_404(client):
    assert client.get("/runs/does-not-exist/report").status_code == 404


# --- compare + audit -------------------------------------------------------


def test_compare_page_ranks_runs(client):
    client.post("/api/runs", json={"strategy": STRAT, "n_positions": 10})
    _wait_runs(client, 1)
    r = client.get("/compare")
    assert r.status_code == 200 and "다중검정 PBO 분석" in r.text and STRAT in r.text


def test_pbo_analysis_runs_and_report_served(client):
    assert client.get("/compare/report").status_code == 404      # before analysis
    resp = client.post("/api/compare", json={})
    assert resp.status_code == 202                                # enqueued
    _wait_jobs_settled(client)
    assert client.get("/compare/report").status_code == 200
    assert "과최적화 확률" in client.get("/compare").text


def test_audit_lists_trials_including_the_run(client):
    client.post("/api/runs", json={"strategy": STRAT, "n_positions": 10})
    _wait_runs(client, 1)
    r = client.get("/audit")
    assert r.status_code == 200
    assert "시도 로그" in r.text and STRAT in r.text
    assert "홀드아웃" in r.text          # holdout section present (locked banner)


# --- run management (detail / delete / rerun / cancel) ---------------------


def test_store_delete_removes_record_and_dir(tmp_path):
    store = RunStore(tmp_path)
    rec = run_synthetic_backtest(store, strategy=STRAT, n_shuffles=8)
    assert store.report_path(rec.id) is not None
    assert store.delete(rec.id) is True
    assert store.get(rec.id) is None
    assert not (tmp_path / "runs" / rec.id).exists()
    assert store.delete("nope") is False          # idempotent on a missing id


def test_run_detail_then_delete(client):
    client.post("/api/runs", json={"strategy": STRAT, "n_positions": 10})
    rid = _wait_runs(client, 1)[0]["id"]

    detail = client.get(f"/runs/{rid}")
    assert detail.status_code == 200 and STRAT in detail.text and "리포트" in detail.text
    assert client.get("/runs/does-not-exist").status_code == 404

    resp = client.post(f"/runs/{rid}/delete", follow_redirects=False)
    assert resp.status_code == 303
    assert client.get("/api/runs").json() == []
    assert client.get(f"/runs/{rid}").status_code == 404


def test_rerun_synthetic_enqueues_second_run(client):
    client.post("/api/runs", json={"strategy": STRAT, "n_positions": 10})
    rid = _wait_runs(client, 1)[0]["id"]
    resp = client.post(f"/runs/{rid}/rerun", follow_redirects=False)
    assert resp.status_code == 303
    _wait_runs(client, 2)                          # a second run appears


def test_run_nl_backtest_generates_dsl_runs_and_comments(tmp_path):
    from quantlab.web.service import run_nl_backtest

    store = RunStore(tmp_path)
    rec = run_nl_backtest(store, idea="최근 20일 오른 종목을 산다", client=FakeLLM(), n_shuffles=8)
    assert rec.source == "nl"
    assert "returns(close, 20)" in rec.note                # generated DSL captured
    html = store.report_path(rec.id).read_text(encoding="utf-8")
    assert "테스트 해설" in html and "해설" in html          # LLM commentary embedded


def test_nl_requires_client(tmp_path):
    from quantlab.web.service import run_nl_backtest

    with pytest.raises(ValueError):
        run_nl_backtest(RunStore(tmp_path), idea="x", client=None, n_shuffles=5)


def test_dashboard_nl_option_gated_on_llm(client, client_llm):
    assert "LLM 미설정" in client.get("/").text            # disabled without a client
    assert "자연어 아이디어 (LLM)" in client_llm.get("/").text


def test_nl_endpoint_runs_with_injected_client(client_llm):
    resp = client_llm.post(
        "/api/runs", data={"source": "nl", "idea": "거래량이 급증한 종목을 산다"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    runs = _wait_runs(client_llm, 1)
    assert runs[0]["source"] == "nl" and runs[0]["note"]


def test_nl_endpoint_422_without_client(client):
    resp = client.post("/api/runs", data={"source": "nl", "idea": "무언가"},
                       follow_redirects=False)
    assert resp.status_code == 422


def test_commentary_embedded_in_synthetic_run_when_client_present(client_llm):
    client_llm.post("/api/runs", json={"strategy": STRAT, "n_positions": 10})
    rid = _wait_runs(client_llm, 1)[0]["id"]
    assert "테스트 해설" in client_llm.get(f"/runs/{rid}/report").text


def test_jobqueue_cancels_queued_but_not_running():
    import threading
    import time

    from quantlab.web.jobs import JobQueue

    q = JobQueue(max_workers=1)
    gate = threading.Event()
    a = q.submit("x", "blocker", lambda: (gate.wait(5), None)[1])
    for _ in range(100):                           # wait until 'a' occupies the worker
        if q.get(a.id).status == "running":
            break
        time.sleep(0.02)
    b = q.submit("x", "queued", lambda: None)       # stuck behind 'a'
    assert q.cancel(b.id) is True and q.get(b.id).status == "cancelled"
    assert q.cancel(a.id) is False                  # running can't be interrupted
    gate.set()
    q.shutdown()
