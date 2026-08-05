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

from datetime import date

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

    record = _record_from_out(
        out, id=run_id, created_at=created, strategy=strategy, source="synthetic",
        n_positions=n_positions,
    )
    store.append(record)
    return record


def run_csv_backtest(
    store: RunStore,
    *,
    csv_path: str | Path,
    config_yaml: str,
    start: date,
    end: date,
    n_shuffles: int = 50,
    ticker_col: str = "Name",
    data_label: str = "CSV real data",
) -> RunRecord:
    """Backtest a DSL strategy on a downloaded OHLCV CSV via :class:`CsvDataSource`.

    Runs the *same* real-data path as live KRX (``run_backtest``): point-in-time
    universe → adjusted panels → DSL alpha → backtest → integrity → report. The
    result is persisted with the identical :class:`RunRecord` shape as a synthetic
    run, so both kinds of run share the dashboard's list/report views.
    """
    from quantlab.data.csv_source import CsvDataSource
    from quantlab.dsl.config import StrategyConfig
    from quantlab.run import run_backtest

    source = CsvDataSource.from_csv(csv_path, ticker_col=ticker_col)
    config = StrategyConfig.from_yaml(config_yaml)

    created = _now_iso()
    label = config.content_hash()
    run_id = RunRecord.new_id(created, f"csv-{label[:8]}")
    run_dir = store.run_dir(run_id)

    out = run_backtest(
        source, config, start=start, end=end,
        cache_dir=store.base / "cache" / run_id, out_dir=run_dir,
        n_shuffles=n_shuffles, data_label=data_label,
        trials_path=store.base / "trials.jsonl",   # one shared log → complete trial count
    )
    record = _record_from_out(
        out, id=run_id, created_at=created, strategy=f"csv:{label[:8]}", source="csv",
        n_positions=int(getattr(config.portfolio, "n_positions", 0)),
        universe_size=int(out.get("universe_size", 0)),
        window=f"{start:%Y-%m-%d}→{end:%Y-%m-%d}",
    )
    store.append(record)
    return record


def run_pbo_comparison(store: RunStore) -> dict:
    """Run the multiple-testing PBO/DSR analysis over the hand-crafted strategy set.

    PBO and the Deflated Sharpe only mean something *across many candidates on one
    dataset*, so this wraps the existing ``run_comparison`` (7 strategies, synthetic
    data). Persists a small summary (``compare/pbo.json``) the Compare page reads,
    and a full comparison report served at ``/compare/report``.
    """
    import json

    from quantlab.demo import run_comparison

    out_dir = store.base / "compare"
    out = run_comparison(out_dir)          # writes comparison.html into out_dir
    summary = {
        "created_at": _now_iso(),
        "pbo": float(out["pbo"].pbo),
        "overfit": bool(out["pbo"].overfit),
        "dsr": float(out["dsr"]),
        "best": str(out["best"]),
        "n_strategies": int(out["n"]),
        "report_file": "comparison.html",
    }
    (out_dir / "pbo.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    return summary


def latest_pbo(store: RunStore) -> dict | None:
    import json

    p = store.base / "compare" / "pbo.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def compare_report_path(store: RunStore):
    p = store.base / "compare" / "comparison.html"
    return p if p.exists() else None


def read_trials(store: RunStore) -> list[dict]:
    """All logged trials (failures included), newest first."""
    import json

    p = store.base / "trials.jsonl"
    if not p.exists():
        return []
    out = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    out.reverse()
    return out


def read_holdout_audit(store: RunStore) -> list[dict]:
    """Holdout access records, newest first (empty if the vault was never unlocked)."""
    import json

    p = store.base / "holdout_audit.jsonl"
    if not p.exists():
        return []
    out = [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    out.reverse()
    return out


def _record_from_out(out: dict, *, id: str, created_at: str, strategy: str, source: str,
                     n_positions: int, universe_size: int = 0, window: str = "") -> RunRecord:
    """Map an evaluation/backtest ``out`` dict onto a persisted RunRecord."""
    s = out["stats"]
    shuf = out["shuffle"]
    return RunRecord(
        id=id, created_at=created_at, strategy=strategy, source=source,
        n_positions=n_positions,
        cagr=float(s["cagr"]), sharpe=float(s["sharpe"]),
        max_drawdown=float(s["max_drawdown"]), total_return=float(s["total_return"]),
        shuffle_p=float(shuf.p_value), survives=bool(shuf.survives),
        trials_logged=int(out["trials_logged"]), report_file="report.html",
        universe_size=universe_size, window=window,
    )
