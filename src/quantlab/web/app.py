"""FastAPI application factory for the dashboard.

Routes are intentionally few for this first slice:
    GET  /                     dashboard (recent runs + new-run form)
    POST /api/runs             trigger a synthetic backtest (form or JSON)
    GET  /api/runs             list run records as JSON
    GET  /runs/{id}/report     serve the run's self-contained HTML report
    GET  /health               liveness probe

``create_app`` takes the runs directory so tests can point it at a tmp path.
FastAPI is imported lazily inside the factory, keeping ``quantlab.web`` importable
without the web extra installed.
"""

from pathlib import Path
from typing import Optional, Union

from quantlab.web.pages import dashboard_page
from quantlab.web.service import available_strategies, run_synthetic_backtest
from quantlab.web.store import RunStore


def create_app(runs_dir: Optional[Union[str, Path]] = None, *, n_shuffles: int = 50):
    from fastapi import FastAPI, Form, HTTPException, Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

    if runs_dir is None:
        from quantlab.config import get_settings
        runs_dir = get_settings().experiments_dir / "web"
    store = RunStore(runs_dir)

    app = FastAPI(title="AI Quant Lab", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> HTMLResponse:
        return HTMLResponse(dashboard_page(store.list(), available_strategies()))

    @app.get("/api/runs", response_class=JSONResponse)
    def list_runs() -> JSONResponse:
        from dataclasses import asdict
        return JSONResponse([asdict(r) for r in store.list()])

    @app.post("/api/runs")
    async def create_run(request: Request):
        # Accept either an HTML form post (redirect back) or a JSON body (return JSON).
        ctype = request.headers.get("content-type", "")
        if "application/json" in ctype:
            payload = await request.json()
            strategy = payload.get("strategy")
            n_positions = int(payload.get("n_positions", 20))
            wants_json = True
        else:
            form = await request.form()
            strategy = form.get("strategy")
            n_positions = int(form.get("n_positions", 20))
            wants_json = False

        if not strategy:
            raise HTTPException(status_code=422, detail="strategy is required")
        try:
            record = run_synthetic_backtest(
                store, strategy=strategy, n_positions=n_positions, n_shuffles=n_shuffles,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        if wants_json:
            from dataclasses import asdict
            return JSONResponse(asdict(record), status_code=201)
        return RedirectResponse(url="/", status_code=303)

    @app.get("/runs/{run_id}/report", response_class=HTMLResponse)
    def run_report(run_id: str):
        path = store.report_path(run_id)
        if path is None:
            raise HTTPException(status_code=404, detail="report not found")
        return FileResponse(path, media_type="text/html")

    return app
