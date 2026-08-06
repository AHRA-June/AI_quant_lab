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
from tests.fakes import RichFakeDataSource


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


def _enqueue_and_drain(client):
    """Enqueue one synthetic run, wait for it, and return its run id."""
    client.post("/api/runs", json={"strategy": STRAT, "n_positions": 12})
    return _wait_runs(client, 1)[0]["id"]

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


def test_dashboard_has_custom_calendar_and_preset_builder(client):
    """Real-data form uses the self-contained day-picker + preset builder,
    not a raw native date input or a mandatory YAML box."""
    html = client.get("/").text
    assert '<input type="date"' not in html          # replaced by custom calendar
    assert 'data-name="start"' in html and 'data-name="end"' in html
    assert 'function qcal' in html                    # calendar JS shipped
    assert 'id="preset-select"' in html               # friendly strategy picker
    assert "DSL 수식 직접 편집" in html                # YAML demoted to advanced


def test_all_dashboard_presets_compile_to_valid_configs():
    """Every alpha the preset builder can emit is a valid DSL config."""
    from quantlab.dsl.config import StrategyConfig

    alphas = [
        "rank(returns(close, 120)) * rank(ts_mean(volume, 20) / ts_mean(volume, 60))",
        "rank(returns(close, 120))",
        "rank(-returns(close, 5))",
        "rank(-ts_std(returns(close, 1), 20))",
        "rank(ts_mean(value, 5) / ts_mean(value, 60))",
    ]
    for alpha in alphas:
        for mk in ("[KOSPI]", "[KOSPI, KOSDAQ]"):
            cfg = StrategyConfig.from_yaml(
                f'alpha: "{alpha}"\n'
                f"universe: {{market: {mk}, top_mktcap: 100, min_turnover: 1e7}}\n"
                f"portfolio: {{n_positions: 20, weighting: equal, rebalance: monthly}}"
            )
            assert cfg.alpha == alpha


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


def test_run_screen_finds_matches_and_backtests(tmp_path):
    from datetime import date

    from quantlab.web.service import read_screen, run_screen
    from tests.fakes import RichFakeDataSource

    cfg = (
        'alpha: "close"\n'
        "universe: {market: [KOSPI], top_mktcap: 20, min_turnover: 1e8}\n"
        "portfolio: {n_positions: 5, weighting: equal, rebalance: weekly}\n"
    )
    store = RunStore(tmp_path)
    rec = run_screen(                                    # direct expr → no LLM needed
        store, source=RichFakeDataSource(), config_yaml=cfg,
        start=date(2021, 7, 1), end=date(2022, 12, 31),
        screen_expr="close > ts_mean(close, 20)", n_shuffles=8,
    )
    assert rec.source == "screen"
    snap = read_screen(store, rec.id)
    assert rec.n_positions == len(snap["matches"]) and snap["ref_date"]
    assert store.report_path(rec.id).exists()           # matches also get a backtest report


def test_screen_endpoint_direct_expr_no_llm(client, tmp_path):
    assert "종목 찾기" in client.get("/screen").text
    csv = _write_long_csv(tmp_path / "s.csv")
    with csv.open("rb") as fh:
        resp = client.post(                              # client fixture has NO llm client
            "/api/screen",
            data={"source": "csv", "start": "2022-06-01", "end": "2023-06-01",
                  "screen_expr": "close > ts_mean(close, 20)", "config_yaml": _CSV_CFG},
            files={"csv": ("s.csv", fh, "text/csv")}, follow_redirects=False,
        )
    assert resp.status_code == 303
    rid = _wait_runs(client, 1)[0]["id"]
    res = client.get(f"/screen/{rid}")
    assert res.status_code == 200 and "매칭 종목" in res.text


def test_screen_matches_csv_export(client, tmp_path):
    csv_file = _write_long_csv(tmp_path / "s.csv")
    with csv_file.open("rb") as fh:
        client.post(
            "/api/screen",
            data={"source": "csv", "start": "2022-06-01", "end": "2023-06-01",
                  "screen_expr": "close > ts_mean(close, 20)", "config_yaml": _CSV_CFG},
            files={"csv": ("s.csv", fh, "text/csv")}, follow_redirects=False,
        )
    rid = _wait_runs(client, 1)[0]["id"]
    resp = client.get(f"/screen/{rid}/matches.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert "ticker,name,close" in resp.text            # header row present


def test_screen_requires_a_condition(client):
    resp = client.post(
        "/api/screen",
        data={"source": "csv", "start": "2022-06-01", "end": "2023-06-01"},
        follow_redirects=False,
    )
    assert resp.status_code == 422                        # neither NL nor expr given


def test_run_krx_backtest_with_injected_source(tmp_path):
    from datetime import date

    from quantlab.web.service import run_krx_backtest
    from tests.fakes import RichFakeDataSource

    cfg = (
        'alpha: "rank(returns(close, 20)) * rank(ts_mean(volume, 5) / ts_mean(volume, 20))"\n'
        "universe: {market: [KOSPI], top_mktcap: 20, min_turnover: 1e8}\n"
        "portfolio: {n_positions: 5, weighting: equal, rebalance: weekly}\n"
    )
    store = RunStore(tmp_path)
    rec = run_krx_backtest(
        store, config_yaml=cfg, start=date(2021, 7, 1), end=date(2022, 12, 31),
        n_shuffles=8, source=RichFakeDataSource(),      # inject fake → no network/pykrx
    )
    assert rec.source == "krx" and rec.universe_size == 20
    assert rec.window == "2021-07-01→2022-12-31"
    assert store.report_path(rec.id).exists()


def test_krx_gated_when_pykrx_absent(client):
    from quantlab.web.service import krx_available

    if krx_available():                                  # env-dependent
        pytest.skip("pykrx is installed")
    assert "pykrx 미설치" in client.get("/").text          # option disabled with a hint
    resp = client.post(
        "/api/runs",
        data={"source": "krx", "start": "2021-07-01", "end": "2022-12-31", "config_yaml": "x"},
        follow_redirects=False,
    )
    assert resp.status_code == 422                        # can't run without the extra


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


# --- Reproducibility bundle ------------------------------------------------


def test_synthetic_run_writes_reproducible_bundle(tmp_path):
    from quantlab.web.repro import read_bundle

    store = RunStore(tmp_path)
    rec = run_synthetic_backtest(store, strategy=STRAT, n_positions=15, n_shuffles=8)
    b = read_bundle(store, rec.id)
    assert b is not None
    assert b["kind"] == "synthetic" and b["reproducible"] is True
    assert len(b["fingerprint"]) == 16
    assert b["inputs"]["strategy"] == STRAT and b["inputs"]["n_positions"] == 15
    assert b["seeds"] == {"synthetic_market": 42, "shuffle": 0}
    assert "quantlab" in b["version"] and "python" in b["version"]
    assert b["verification"] is None


def test_fingerprint_is_deterministic_across_runs(tmp_path):
    from quantlab.web.repro import read_bundle

    s1 = RunStore(tmp_path / "a")
    s2 = RunStore(tmp_path / "b")
    r1 = run_synthetic_backtest(s1, strategy=STRAT, n_positions=15, n_shuffles=8)
    r2 = run_synthetic_backtest(s2, strategy=STRAT, n_positions=15, n_shuffles=8)
    assert read_bundle(s1, r1.id)["fingerprint"] == read_bundle(s2, r2.id)["fingerprint"]


def test_reproduce_run_matches_and_stamps_verdict(tmp_path):
    from quantlab.web.repro import read_bundle, reproduce_run

    store = RunStore(tmp_path)
    rec = run_synthetic_backtest(store, strategy=STRAT, n_positions=15, n_shuffles=8)
    v = reproduce_run(store, rec.id)
    assert v["matches"] is True
    assert len(v["reproduced_fingerprint"]) == 16
    # verdict is stamped back into the bundle on disk
    assert read_bundle(store, rec.id)["verification"]["matches"] is True


def test_csv_run_pins_data_and_is_reproducible(tmp_path):
    from datetime import date

    from quantlab.web.repro import PIN_DIR, read_bundle, reproduce_run

    store = RunStore(tmp_path)
    csv = _write_long_csv(tmp_path / "prices.csv")
    rec = run_csv_backtest(
        store, csv_path=csv, config_yaml=_CSV_CFG,
        start=date(2022, 6, 1), end=date(2023, 6, 1), n_shuffles=8,
    )
    b = read_bundle(store, rec.id)
    assert b["kind"] == "csv" and b["reproducible"] is True
    assert b["inputs"]["data_sha256"] and b["inputs"]["config_yaml"] == _CSV_CFG
    # the source CSV is copied into the run so re-runs need no external file
    pinned = store.base / "runs" / rec.id / PIN_DIR / "prices.csv"
    assert pinned.exists()
    # re-running from the pinned copy reproduces the exact fingerprint
    v = reproduce_run(store, rec.id)
    assert v["matches"] is True
    assert read_bundle(store, rec.id)["verification"]["matches"] is True


def test_reproduce_detects_tampered_pinned_data(tmp_path):
    from datetime import date

    from quantlab.web.repro import PIN_DIR, reproduce_run

    store = RunStore(tmp_path)
    csv = _write_long_csv(tmp_path / "prices.csv")
    rec = run_csv_backtest(
        store, csv_path=csv, config_yaml=_CSV_CFG,
        start=date(2022, 6, 1), end=date(2023, 6, 1), n_shuffles=8,
    )
    pinned = store.base / "runs" / rec.id / PIN_DIR / "prices.csv"
    pinned.write_text(pinned.read_text(encoding="utf-8") + "\n# tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="해시 불일치"):
        reproduce_run(store, rec.id)


def test_reproduce_non_reproducible_bundle_is_rejected(tmp_path):
    import json

    from quantlab.web.repro import reproduce_run

    store = RunStore(tmp_path)
    rec = run_synthetic_backtest(store, strategy=STRAT, n_positions=15, n_shuffles=8)
    bp = store.base / "runs" / rec.id / "bundle.json"
    b = json.loads(bp.read_text(encoding="utf-8"))
    b["reproducible"] = False   # e.g. an external-data (nl/krx/screen) run
    bp.write_text(json.dumps(b), encoding="utf-8")
    with pytest.raises(ValueError):
        reproduce_run(store, rec.id)


def test_bundle_json_endpoint_serves_attachment(client):
    rid = _enqueue_and_drain(client)
    r = client.get(f"/runs/{rid}/bundle.json")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert r.json()["kind"] == "synthetic"


def test_reproduce_endpoint_redirects_and_detail_shows_verdict(client):
    rid = _enqueue_and_drain(client)
    r = client.post(f"/runs/{rid}/reproduce", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/runs/{rid}"
    detail = client.get(f"/runs/{rid}").text
    assert "재현성 번들" in detail and "지문 일치" in detail


def test_bundle_json_missing_run_404(client):
    assert client.get("/runs/does-not-exist/bundle.json").status_code == 404


# --- KRX explicit-basket path (snapshot endpoints unavailable) --------------


class _SnapshotDeadKRX(RichFakeDataSource):
    """Models the user's broken KRX: the cross-sectional *snapshot* endpoints
    (market cap / whole-market ticker list / ETF list) are dead, while per-ticker
    OHLCV still works. Any accidental snapshot call fails the test loudly."""

    def get_market_cap(self, on, market):
        raise AssertionError("get_market_cap must not be called on the KRX basket path")

    def get_ticker_list(self, on, market):
        raise AssertionError("get_ticker_list must not be called on the KRX basket path")

    def get_etf_etn_ticker_list(self, on):
        raise AssertionError("get_etf_etn_ticker_list must not be called on the KRX basket path")


class _KRXWithDeadTicker(_SnapshotDeadKRX):
    """One basket ticker (999999) has no data — reproduces the KeyError: 'close'
    scenario. Its empty frame carries canonical columns, as the fixed pykrx
    normalizer guarantees, so the pipeline must simply skip it, not crash."""

    DEAD = "999999"
    _CANON = ["open", "high", "low", "close", "volume", "value"]

    def get_ohlcv(self, ticker, start, end):
        if ticker == self.DEAD:
            return pd.DataFrame(columns=self._CANON)
        return super().get_ohlcv(ticker, start, end)

    def get_adjusted_close(self, ticker, start, end):
        if ticker == self.DEAD:
            return pd.Series(dtype="float64", name="close")
        return super().get_adjusted_close(ticker, start, end)


def test_krx_basket_survives_a_ticker_with_no_data(tmp_path):
    from datetime import date

    from quantlab.web.service import run_krx_backtest

    store = RunStore(tmp_path)
    basket = ["100000", "100010", "999999", "100020"]     # 999999 returns nothing
    rec = run_krx_backtest(
        store, config_yaml=_CSV_CFG, start=date(2021, 6, 1), end=date(2022, 6, 1),
        n_shuffles=6, source=_KRXWithDeadTicker(), tickers=basket,
    )
    assert rec.source == "krx" and store.report_path(rec.id).exists()


def test_parse_tickers_normalizes_and_dedupes():
    from quantlab.web.service import parse_tickers

    assert parse_tickers("005930, 000660\n035420 005930") == ["005930", "000660", "035420"]
    assert parse_tickers("5930, 660") == ["005930", "000660"]      # zero-pad to 6
    assert parse_tickers("삼성, abc, 12345") == ["012345"]          # words dropped, digits padded
    assert parse_tickers("") == [] and parse_tickers(None) == []


def test_krx_backtest_uses_explicit_basket_without_snapshot_endpoints(tmp_path):
    from datetime import date

    from quantlab.web.service import run_krx_backtest

    store = RunStore(tmp_path)
    basket = ["100000", "100010", "100020", "100030", "100040", "100050"]
    rec = run_krx_backtest(
        store, config_yaml=_CSV_CFG, start=date(2021, 6, 1), end=date(2022, 6, 1),
        n_shuffles=6, source=_SnapshotDeadKRX(), tickers=basket,
    )
    assert rec.source == "krx"
    assert rec.universe_size == len(basket)      # exactly the basket, no ranking
    assert store.report_path(rec.id).exists()
    from quantlab.web.repro import read_bundle
    assert read_bundle(store, rec.id)["inputs"]["tickers"] == basket


def test_krx_backtest_without_basket_falls_back_to_auto_universe(tmp_path):
    """No explicit basket → UniverseBuilder path (works when snapshots are up)."""
    from datetime import date

    from quantlab.web.service import run_krx_backtest

    store = RunStore(tmp_path)
    rec = run_krx_backtest(
        store, config_yaml=_CSV_CFG, start=date(2021, 6, 1), end=date(2022, 6, 1),
        n_shuffles=6, source=RichFakeDataSource(), tickers=None,   # snapshots available here
    )
    assert rec.source == "krx" and rec.universe_size == 20         # top_mktcap from _CSV_CFG


def test_dashboard_shows_krx_ticker_field_with_defaults(client):
    html = client.get("/").text
    assert 'id="fields-krx"' in html
    assert 'name="tickers"' in html
    assert "005930" in html            # default basket pre-filled (Samsung Electronics)


# --- screener fixes: visible failures, presets, KRX basket, friendly errors --


def test_screen_page_shows_presets_and_krx_ticker_box(client):
    html = client.get("/screen").text
    assert 'id="scr-preset"' in html                     # one-click condition picker
    assert "20일선 위 + 거래량 급등" in html               # a preset label
    assert 'id="scr-krx"' in html and 'name="tickers"' in html and "005930" in html


def test_screen_failure_is_surfaced_on_the_page(client, tmp_path):
    # a Korean sentence in the direct-expression box is not valid DSL → the job
    # fails; the failure (and its message) must show up on /screen, not vanish.
    csv = _write_long_csv(tmp_path / "s.csv")
    with csv.open("rb") as fh:
        client.post(
            "/api/screen",
            data={"source": "csv", "start": "2022-06-01", "end": "2023-06-01",
                  "screen_expr": "20일평균선 초과 & 거래량 급등", "config_yaml": _CSV_CFG},
            files={"csv": ("s.csv", fh, "text/csv")}, follow_redirects=False,
        )
    _wait_jobs_settled(client)
    page = client.get("/screen").text
    assert "실행 중 작업" in page and "실패" in page        # failure card rendered
    assert "조건식을 해석하지 못했습니다" in page            # with the friendly message


def test_run_screen_bad_expr_raises_friendly_error(tmp_path):
    from datetime import date

    from quantlab.web.service import run_screen

    store = RunStore(tmp_path)
    with pytest.raises(ValueError, match="조건식을 해석하지 못했습니다"):
        run_screen(store, source=RichFakeDataSource(), config_yaml=_CSV_CFG,
                   start=date(2021, 7, 1), end=date(2022, 12, 31),
                   screen_expr="20일평균선 초과 & 거래량 급등", n_shuffles=6)


def test_run_screen_krx_basket_skips_snapshot_endpoints(tmp_path):
    from datetime import date

    from quantlab.web.service import run_screen

    store = RunStore(tmp_path)
    rec = run_screen(
        store, source=_SnapshotDeadKRX(), config_yaml=_CSV_CFG,
        start=date(2021, 7, 1), end=date(2022, 12, 31),
        screen_expr="close > ts_mean(close, 20)",
        tickers=["100000", "100010", "100020", "100030"], n_shuffles=6,
    )
    assert rec.source == "screen" and rec.universe_size == 4
    assert store.report_path(rec.id).exists()


def test_all_screen_presets_compile():
    from quantlab.dsl.screen import compile_screen
    from quantlab.web.pages import _SCREEN_PRESETS

    for _key, _label, expr in _SCREEN_PRESETS:
        compile_screen(expr)                             # raises if any preset is invalid


# --- natural-language screening without an LLM key + wider KRX universe -------


@pytest.mark.parametrize("phrase", [
    "골든크로스",
    "20일선 위이면서 거래량이 2배 이상",
    "20일선 위 그리고 거래량 급등",
    "거래량 3배 이상",
    "60일 신고가",
    "20일 신고가 또는 거래량 급증",
    "최근 20일 10% 이상 상승",
    "5일 상승",
    "데드크로스 그리고 20일선 아래",
])
def test_nl_screen_translates_to_valid_dsl(phrase):
    """Every supported Korean phrase compiles under the screen whitelist — so the
    natural-language box works with no LLM key at all."""
    from quantlab.dsl.nl_screen import nl_to_screen_expr
    from quantlab.dsl.screen import compile_screen

    compile_screen(nl_to_screen_expr(phrase))            # raises if the output is invalid


def test_nl_screen_unrecognized_raises_friendly_error():
    from quantlab.dsl.nl_screen import NlScreenError, nl_to_screen_expr

    with pytest.raises(NlScreenError, match="이해하지 못했습니다"):
        nl_to_screen_expr("맛있는 라면 관련 종목")


def test_run_screen_natural_language_without_client(tmp_path):
    """criteria + client=None → the rule-based translator runs the screen; no
    LLM required (previously this raised 'LLM is not configured')."""
    from datetime import date

    from quantlab.web.service import read_screen, run_screen

    store = RunStore(tmp_path)
    rec = run_screen(
        store, source=RichFakeDataSource(), config_yaml=_CSV_CFG,
        start=date(2021, 7, 1), end=date(2022, 12, 31),
        criteria="20일선 위", client=None, n_shuffles=6,
    )
    snap = read_screen(store, rec.id)
    assert snap["expr"] == "close > ts_mean(close, 20)"   # translated, not LLM-generated
    assert snap["criteria"] == "20일선 위"                  # original kept for display


def test_screen_endpoint_natural_language_no_llm(client, tmp_path):
    """POST a Korean phrase (no direct expr, no LLM client) → the job runs and
    the result page lists matches."""
    csv = _write_long_csv(tmp_path / "s.csv")
    with csv.open("rb") as fh:
        resp = client.post(
            "/api/screen",
            data={"source": "csv", "start": "2022-06-01", "end": "2023-06-01",
                  "criteria": "20일선 위", "config_yaml": _CSV_CFG},
            files={"csv": ("s.csv", fh, "text/csv")}, follow_redirects=False,
        )
    assert resp.status_code == 303
    rid = _wait_runs(client, 1)[0]["id"]
    assert "매칭 종목" in client.get(f"/screen/{rid}").text


def test_screen_endpoint_bad_nl_returns_422_synchronously(client, tmp_path):
    """An unrecognised Korean phrase gets a friendly 422 up front, not a silent
    failed job."""
    csv = _write_long_csv(tmp_path / "s.csv")
    with csv.open("rb") as fh:
        resp = client.post(
            "/api/screen",
            data={"source": "csv", "start": "2022-06-01", "end": "2023-06-01",
                  "criteria": "맛있는 라면 종목", "config_yaml": _CSV_CFG},
            files={"csv": ("s.csv", fh, "text/csv")}, follow_redirects=False,
        )
    assert resp.status_code == 422 and "이해하지 못했습니다" in resp.text


def test_resolve_krx_universe_returns_market_tickers(tmp_path):
    from datetime import date

    from quantlab.web.service import resolve_krx_universe

    codes = resolve_krx_universe(RichFakeDataSource(), "kospi", date(2022, 12, 30))
    assert len(codes) > 20 and all(c.isdigit() for c in codes)   # far past the 33 basket


def test_resolve_krx_universe_friendly_error_when_list_endpoint_down(tmp_path):
    from datetime import date

    from quantlab.web.service import resolve_krx_universe

    with pytest.raises(ValueError, match="목록을 불러오지 못했습니다"):
        resolve_krx_universe(_SnapshotDeadKRX(), "all", date(2022, 12, 30))


def test_screen_page_offers_nl_box_and_universe_selector_without_llm(client):
    """Even with no LLM key, the natural-language box is present and the KRX
    universe selector lets users go beyond the default basket."""
    html = client.get("/screen").text
    assert 'name="criteria"' in html                      # NL box always available now
    assert "규칙 기반" in html                              # no-key hint
    assert 'name="krx_universe"' in html and "코스피 전체" in html
