"""Backtest orchestration for the dashboard.

Composes the existing synthetic pipeline (strategy → weights → backtest →
integrity → report) and persists the result as a :class:`RunRecord`. This is the
only place the web layer touches the research core; everything analytical is
reused, not reimplemented.

First slice: synthetic data only, so a run is fast and needs no network. Wiring a
:class:`~quantlab.data.csv_source.CsvDataSource` / live KRX source through
``run_backtest`` is a later slice (same record shape).
"""

from __future__ import annotations

from pathlib import Path

from quantlab.demo import (
    STRATEGIES,
    _evaluate,
    synthetic_market,
    write_strategy_report,
)
from quantlab.factors.portfolio import top_n_long_only
from quantlab.web.store import RunRecord, RunStore, _now_iso


def available_strategies() -> list[str]:
    return list(STRATEGIES)


def run_synthetic_backtest(
    store: RunStore,
    *,
    strategy: str,
    n_positions: int = 20,
    n_shuffles: int = 50,
    trials_path: str | Path | None = None,
) -> RunRecord:
    """Run one hand-crafted strategy on synthetic data, persist + return its record."""
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; choose from {available_strategies()}")

    trials_path = Path(trials_path) if trials_path else store.base / "trials.jsonl"

    close, volume = synthetic_market()
    fn, needs_vol = STRATEGIES[strategy]
    alpha = fn(close, volume) if needs_vol else fn(close)
    weights = top_n_long_only(alpha, n_positions=n_positions)
    out = _evaluate(alpha, weights, close, trials_path, n_shuffles, label=strategy)

    created = _now_iso()
    run_id = RunRecord.new_id(created, strategy)
    run_dir = store.run_dir(run_id)
    write_strategy_report(
        out, close, run_dir,
        subtitle=f"{strategy} · 합성 데이터 · 종목 {n_positions}개",
    )

    s = out["stats"]
    shuf = out["shuffle"]
    record = RunRecord(
        id=run_id,
        created_at=created,
        strategy=strategy,
        source="synthetic",
        n_positions=n_positions,
        cagr=float(s["cagr"]),
        sharpe=float(s["sharpe"]),
        max_drawdown=float(s["max_drawdown"]),
        total_return=float(s["total_return"]),
        shuffle_p=float(shuf.p_value),
        survives=bool(shuf.survives),
        trials_logged=int(out["trials_logged"]),
        report_file="report.html",
    )
    store.append(record)
    return record
