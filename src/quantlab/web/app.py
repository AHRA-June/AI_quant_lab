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
from quantlab.web.pages import audit_page, compare_page, dashboard_page, run_detail_page
from quantlab.web.service import (
    available_strategies,
    compare_report_path,
    latest_pbo,
    read_holdout_audit,
    read_trials,
    run_csv_backtest,
    run_pbo_comparison,
    run_synthetic_backtest,
)
from quantlab.web.store import RunStore


def create_app(runs_dir: Optional[Union[str, Path]] = None, *, n_shuffles: int = 50,
               max_workers: int = 2):
    from contextlib import asynccontextmanager

    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

    if runs_dir is None:
        from quantlab.config import get_settings
        runs_dir = get_settings().experiments_dir / "web"
    store = RunStore(runs_dir)
    queue = JobQueue(max_workers=max_workers)

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
        return HTMLResponse(dashboard_page(store.list(), available_strategies(), queue.list()))

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
                    store, strategy=strategy, n_positions=n_pos, n_shuffles=n_shuffles).id,
            )
            return JSONResponse({"job_id": job.id, "status": job.status}, status_code=202)

        form = await request.form()
        source = form.get("source", "synthetic")

        if source == "csv":
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
                    start=start_d, end=end_d, n_shuffles=n_shuffles).id,
            )
        else:
            strategy = form.get("strategy")
            if strategy not in available_strategies():
                raise HTTPException(status_code=422, detail="unknown or missing strategy")
            n_pos = int(form.get("n_positions", 20))
            queue.submit(
                "synthetic", strategy,
                lambda: run_synthetic_backtest(
                    store, strategy=strategy, n_positions=n_pos, n_shuffles=n_shuffles).id,
            )

        return RedirectResponse(url="/", status_code=303)

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_detail(run_id: str):
        rec = store.get(run_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="run not found")
        return HTMLResponse(run_detail_page(rec))

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
                store, strategy=strat, n_positions=n_pos, n_shuffles=n_shuffles).id,
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

    # --- integrity audit ---------------------------------------------------

    @app.get("/audit", response_class=HTMLResponse)
    def audit() -> HTMLResponse:
        return HTMLResponse(audit_page(read_trials(store), read_holdout_audit(store)))

    return app
