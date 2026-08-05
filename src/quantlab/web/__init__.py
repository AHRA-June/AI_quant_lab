"""Web dashboard (M5, first slice).

A thin FastAPI layer over the existing research pipeline: trigger a backtest,
persist a run record, and serve the self-contained HTML report — no new analytics
live here, only orchestration and presentation. Kept import-light so the core
package still imports without FastAPI installed (the web extra is optional).
"""
