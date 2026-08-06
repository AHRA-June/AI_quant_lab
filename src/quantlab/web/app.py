"""FastAPI application factory for the dashboard.

Routes:
    GET  /                     dashboard (active jobs + recent runs + new-run form)
    POST /api/runs             enqueue a backtest (form or JSON) → returns a job
    GET  /api/runs             list finished run records as JSON
    GET  /api/jobs             list job statuses as JSON
    GET  /runs/{id}/report     serve a run's self-contained HTML report
    GET  /compare              runs ranked + multiple-testing PBO analysis
    POST /api/compare          enqueue the PBO analysis
    GET  /compare/report       serve the full comparison report
    GET  /audit                trial log (failures included) + holdout audit
    GET  /health               liveness probe

Backtests run on a background job queue so requests return immediately and the UI
stays responsive on long real-data runs; the dashboard polls job status.

``create_app`` takes the runs directory so tests can point it at a tmp path.
FastAPI is imported lazily inside the factory, keeping ``quantlab.web`` importable
without the web extra installed.
"""

from pathlib import Path
from typing import Optional, Union

from quantlab.web.jobs import JobQueue
from quantlab.web.repro import read_bundle, reproduce_run
from quantlab.web.pages import (
    DEFAULT_CONFIG_YAML,
    audit_page,
    compare_page,
    dashboard_page,
    run_detail_page,
    screen_page,
    screen_result_page,
)
from quantlab.web.service import (
    available_strategies,
    compare_report_path,
    get_llm_client,
    krx_available,
    DEFAULT_KRX_TICKERS,
    latest_pbo,
    parse_tickers,
    read_holdout_audit,
    read_trials,
    read_screen,
    resolve_krx_universe,
    run_csv_backtest,
    run_krx_backtest,
    run_nl_backtest,
    run_pbo_comparison,
    run_screen,
    run_synthetic_backtest,
)
from quantlab.web.store import RunStore

_UNSET = object()


def create_app(runs_dir: Optional[Union[str, Path]] = None, *, n_shuffles: int = 50,
               max_workers: int = 2, llm_client=_UNSET):
    from contextlib import asynccontextmanager

    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

    if runs_dir is None:
        from quantlab.config import get_settings
        runs_dir = get_settings().experiments_dir / "web"
    store = RunStore(runs_dir)
    queue = JobQueue(max_workers=max_workers)
    # Inject a client in tests; otherwise auto-detect (None if no key / extra).
    client = get_llm_client() if llm_client is _UNSET else llm_client

    @asynccontextmanager
    async def lifespan(_app):
        yield
        queue.shutdown()

    app = FastAPI(title="AI Quant Lab", version="0.2.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        return HTMLResponse(dashboard_page(
            store.list(), available_strategies(), queue.list(),
            llm_available=client is not None, krx_available=krx_available()))

    @app.get("/api/runs", response_class=JSONResponse)
    def list_runs() -> JSONResponse:
        from dataclasses import asdict
        return JSONResponse([asdict(r) for r in store.list()])

    @app.get("/api/jobs", response_class=JSONResponse)
    def list_jobs() -> JSONResponse:
        return JSONResponse(queue.as_dicts())

    @app.post("/api/runs")
    async def create_run(request: Request):
        from datetime import date

        # Enqueue a backtest. Cheap validation happens synchronously (so bad input
        # is a 422 now); the heavy run is deferred to the worker. JSON → 202 + job,
        # form → redirect to the dashboard where the job shows as running.
        ctype = request.headers.get("content-type", "")
        if "application/json" in ctype:
            payload = await request.json()
            strategy = payload.get("strategy")
            if strategy not in available_strategies():
                raise HTTPException(status_code=422, detail="unknown or missing strategy")
            n_pos = int(payload.get("n_positions", 20))
            job = queue.submit(
                "synthetic", strategy,
                lambda: run_synthetic_backtest(
                    store, strategy=strategy, n_positions=n_pos, n_shuffles=n_shuffles,
                    client=client).id,
            )
            return JSONResponse({"job_id": job.id, "status": job.status}, status_code=202)

        form = await request.form()
        source = form.get("source", "synthetic")

        if source == "nl":
            idea = (form.get("idea") or "").strip()
            if not idea:
                raise HTTPException(status_code=422, detail="아이디어를 입력하세요")
            if client is None:
                raise HTTPException(
                    status_code=422,
                    detail="LLM 미설정 — ANTHROPIC_API_KEY 설정 후 pip install '.[llm]'")
            queue.submit(
                "nl", f"자연어: {idea[:32]}",
                lambda: run_nl_backtest(store, idea=idea, client=client, n_shuffles=n_shuffles).id,
            )
        elif source == "csv":
            upload = form.get("csv")
            if upload is None or not getattr(upload, "filename", ""):
                raise HTTPException(status_code=422, detail="CSV file is required")
            start_s, end_s = form.get("start"), form.get("end")
            if not start_s or not end_s:
                raise HTTPException(status_code=422, detail="start and end dates are required")
            try:
                start_d, end_d = date.fromisoformat(start_s), date.fromisoformat(end_s)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"bad date: {exc}") from exc
            uploads = store.base / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            dest = uploads / upload.filename
            dest.write_bytes(await upload.read())
            cfg = form.get("config_yaml") or ""
            queue.submit(
                "csv", f"csv:{upload.filename}",
                lambda: run_csv_backtest(
                    store, csv_path=dest, config_yaml=cfg,
                    start=start_d, end=end_d, n_shuffles=n_shuffles, client=client).id,
            )
        elif source == "krx":
            if not krx_available():
                raise HTTPException(status_code=422,
                                    detail="KRX 미설치 — pip install '.[data]' 후 사용하세요")
            start_s, end_s = form.get("start"), form.get("end")
            if not start_s or not end_s:
                raise HTTPException(status_code=422, detail="start and end dates are required")
            try:
                start_d, end_d = date.fromisoformat(start_s), date.fromisoformat(end_s)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"bad date: {exc}") from exc
            cfg = form.get("config_yaml") or ""
            krx_tickers = parse_tickers(form.get("tickers")) or None
            queue.submit(
                "krx", f"krx:{start_s}→{end_s}",
                lambda: run_krx_backtest(
                    store, config_yaml=cfg, start=start_d, end=end_d,
                    n_shuffles=n_shuffles, client=client, tickers=krx_tickers).id,
            )
        else:
            strategy = form.get("strategy")
            if strategy not in available_strategies():
                raise HTTPException(status_code=422, detail="unknown or missing strategy")
            n_pos = int(form.get("n_positions", 20))
            queue.submit(
                "synthetic", strategy,
                lambda: run_synthetic_backtest(
                    store, strategy=strategy, n_positions=n_pos, n_shuffles=n_shuffles,
                    client=client).id,
            )

        return RedirectResponse(url="/", status_code=303)

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail(run_id: str):
        rec = store.get(run_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="run not found")
        return HTMLResponse(run_detail_page(rec, read_bundle(store, run_id)))

    @app.get("/runs/{run_id}/bundle.json", response_class=JSONResponse)
    def run_bundle(run_id: str):
        bundle = read_bundle(store, run_id)
        if bundle is None:
            raise HTTPException(status_code=404, detail="bundle not found")
        return JSONResponse(bundle, headers={
            "Content-Disposition": f'attachment; filename="bundle_{run_id}.json"'})

    @app.post("/runs/{run_id}/reproduce")
    def reproduce(run_id: str):
        try:
            reproduce_run(store, run_id)              # re-runs + stamps the verdict
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return RedirectResponse(url=f"/runs/{run_id}", status_code=303)

    @app.get("/runs/{run_id}/report", response_class=HTMLResponse)
    def run_report(run_id: str):
        path = store.report_path(run_id)
        if path is None:
            raise HTTPException(status_code=404, detail="report not found")
        return FileResponse(path, media_type="text/html")

    @app.post("/runs/{run_id}/delete")
    def delete_run(run_id: str):
        store.delete(run_id)
        return RedirectResponse(url="/", status_code=303)

    @app.post("/runs/{run_id}/rerun")
    def rerun_run(run_id: str):
        rec = store.get(run_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="run not found")
        if rec.source != "synthetic":
            raise HTTPException(status_code=422, detail="only synthetic runs can be re-run in place")
        strat, n_pos = rec.strategy, rec.n_positions
        queue.submit(
            "synthetic", strat,
            lambda: run_synthetic_backtest(
                store, strategy=strat, n_positions=n_pos, n_shuffles=n_shuffles,
                client=client).id,
        )
        return RedirectResponse(url="/", status_code=303)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, request: Request):
        ok = queue.cancel(job_id)
        if "application/json" in request.headers.get("content-type", ""):
            return JSONResponse({"cancelled": ok})
        return RedirectResponse(url="/", status_code=303)

    # --- compare (multiple-testing PBO) ------------------------------------

    @app.get("/compare", response_class=HTMLResponse)
    def compare() -> HTMLResponse:
        return HTMLResponse(compare_page(store.list(), latest_pbo(store)))

    @app.post("/api/compare")
    def create_compare(request: Request):
        job = queue.submit("compare", "PBO 분석", lambda: (run_pbo_comparison(store), None)[1])
        if "application/json" in request.headers.get("content-type", ""):
            return JSONResponse({"job_id": job.id, "status": job.status}, status_code=202)
        return RedirectResponse(url="/compare", status_code=303)

    @app.get("/compare/report", response_class=HTMLResponse)
    def compare_report():
        path = compare_report_path(store)
        if path is None:
            raise HTTPException(status_code=404, detail="run the PBO analysis first")
        return FileResponse(path, media_type="text/html")

    # --- screener ----------------------------------------------------------

    @app.get("/screen", response_class=HTMLResponse)
    def screen() -> HTMLResponse:
        return HTMLResponse(screen_page(
            store.list(), jobs=queue.list(), llm_available=client is not None,
            krx_available=krx_available(), default_yaml=DEFAULT_CONFIG_YAML))

    @app.post("/api/screen")
    async def create_screen(request: Request):
        from datetime import date

        form = await request.form()
        start_s, end_s = form.get("start"), form.get("end")
        if not start_s or not end_s:
            raise HTTPException(status_code=422, detail="start and end dates are required")
        try:
            start_d, end_d = date.fromisoformat(start_s), date.fromisoformat(end_s)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"bad date: {exc}") from exc

        criteria = (form.get("criteria") or "").strip() or None
        expr = (form.get("screen_expr") or "").strip() or None
        if not expr and not criteria:
            raise HTTPException(status_code=422, detail="조건(자연어) 또는 직접 조건식을 입력하세요")
        if not expr and client is None:
            # No LLM key → translate the Korean phrase with the rule-based engine
            # up front, so an unrecognised phrase gives a synchronous, friendly
            # error instead of a failed background job.
            from quantlab.dsl.nl_screen import NlScreenError, nl_to_screen_expr
            try:
                expr = nl_to_screen_expr(criteria)
            except NlScreenError as nl_exc:
                raise HTTPException(status_code=422, detail=str(nl_exc)) from nl_exc
        cfg = form.get("config_yaml") or DEFAULT_CONFIG_YAML

        src = form.get("source", "csv")
        screen_tickers = None
        if src == "krx":
            if not krx_available():
                raise HTTPException(status_code=422, detail="KRX 미설치 — pip install '.[data]'")
            from quantlab.data.pykrx_source import PykrxDataSource
            make_source, data_label = (lambda: PykrxDataSource()), "KRX 일봉"
            # Universe: the curated basket (per-ticker fetch, always works) or a
            # whole-market list (kospi/kosdaq/all) so screening isn't capped at a
            # handful of large-caps. resolve_krx_universe raises a friendly error
            # if KRX's list endpoint is down.
            universe = (form.get("krx_universe") or "basket").strip()
            if universe == "basket":
                screen_tickers = parse_tickers(form.get("tickers")) or list(DEFAULT_KRX_TICKERS)
                data_label = f"KRX 일봉 · 바스켓 {len(screen_tickers)}종목"
            else:
                try:
                    screen_tickers = resolve_krx_universe(PykrxDataSource(), universe, end_d)
                except ValueError as u_exc:
                    raise HTTPException(status_code=422, detail=str(u_exc)) from u_exc
                data_label = f"KRX 일봉 · {universe.upper()} 전체 {len(screen_tickers)}종목"
        else:
            upload = form.get("csv")
            if upload is None or not getattr(upload, "filename", ""):
                raise HTTPException(status_code=422, detail="CSV file is required")
            uploads = store.base / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            dest = uploads / upload.filename
            dest.write_bytes(await upload.read())
            from quantlab.data.csv_source import CsvDataSource
            make_source, data_label = (lambda: CsvDataSource.from_csv(dest)), "CSV"

        queue.submit(
            "screen", f"screen:{(criteria or expr)[:24]}",
            lambda: run_screen(
                store, source=make_source(), config_yaml=cfg, start=start_d, end=end_d,
                criteria=criteria, screen_expr=expr, client=client, tickers=screen_tickers,
                n_shuffles=n_shuffles, data_label=data_label).id,
        )
        return RedirectResponse(url="/screen", status_code=303)

    @app.get("/screen/{run_id}", response_class=HTMLResponse)
    def screen_result(run_id: str):
        rec = store.get(run_id)
        snap = read_screen(store, run_id)
        if rec is None or snap is None:
            raise HTTPException(status_code=404, detail="screen not found")
        return HTMLResponse(screen_result_page(rec, snap))

    @app.get("/screen/{run_id}/matches.csv")
    def screen_matches_csv(run_id: str):
        import csv
        import io

        from fastapi.responses import Response

        snap = read_screen(store, run_id)
        if snap is None:
            raise HTTPException(status_code=404, detail="screen not found")
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ticker", "name", "close", "ref_date", "expr"])
        for m in snap.get("matches", []):
            w.writerow([m.get("ticker", ""), m.get("name", ""), m.get("close", ""),
                        snap.get("ref_date", ""), snap.get("expr", "")])
        return Response(
            content="﻿" + buf.getvalue(),          # BOM so Excel reads UTF-8 (Korean) right
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="matches_{run_id}.csv"'},
        )

    # --- integrity audit ---------------------------------------------------

    @app.get("/audit", response_class=HTMLResponse)
    def audit() -> HTMLResponse:
        return HTMLResponse(audit_page(read_trials(store), read_holdout_audit(store)))

    return app
