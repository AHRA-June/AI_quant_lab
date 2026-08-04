"""Assemble a full HTML report from a backtest result + integrity diagnostics.

Ties M4 together: performance metrics, an equity-vs-benchmark chart, a drawdown
chart, and a research-integrity panel (Deflated Sharpe, shuffle control, PBO,
trial count) with pass/fail badges — plus an optional ML panel and LLM
commentary. Everything is written to a single self-contained HTML file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from quantlab.backtest.metrics import cagr
from quantlab.integrity.pbo import PBOResult
from quantlab.integrity.shuffle import ShuffleResult
from quantlab.report.charts import drawdown_chart, line_chart
from quantlab.report.html import _row, render_comparison, render_html


def equal_weight_benchmark(returns: pd.DataFrame) -> pd.Series:
    """Daily-rebalanced equal-weight index equity (benchmark, F5.2).

    Stands in for a market index on synthetic data; on live KRX, swap in the
    actual KOSPI/KOSDAQ series (which are point-in-time and must not be
    reconstructed from the current universe — see PRD §11).
    """
    port = returns.mean(axis=1).fillna(0.0)
    return (1 + port).cumprod()


@dataclass
class ReportInputs:
    label: str
    subtitle: str
    stats: dict                       # summary() output + cost_drag
    equity: pd.Series                 # net-of-cost strategy equity
    benchmark_equity: pd.Series
    dsr: float | None = None
    shuffle: ShuffleResult | None = None
    pbo: PBOResult | None = None
    trials: int | None = None
    ml: dict | None = None            # rank_ic_mean / ic_ir / quantile_spread
    commentary: str | None = None
    extra_metrics: list[tuple[str, str]] = field(default_factory=list)


def _pct(x: float) -> str:
    return f"{x:+.1%}"


def build_report(inp: ReportInputs) -> str:
    s = inp.stats
    metrics = [
        ("Total return", _pct(s["total_return"])),
        ("CAGR", _pct(s["cagr"])),
        ("Sharpe", f"{s['sharpe']:.2f}"),
        ("Sortino", f"{s['sortino']:.2f}"),
        ("Max drawdown", f"{s['max_drawdown']:.1%}"),
        ("Ann. vol", f"{s['ann_vol']:.1%}"),
        ("Avg turnover", f"{s.get('avg_turnover', float('nan')):.2f}"),
        ("Cost drag", f"{s.get('cost_drag', float('nan')):.2%}"),
        *inp.extra_metrics,
    ]

    # Benchmark comparison
    bench_cagr = cagr(inp.benchmark_equity)
    excess = s["cagr"] - bench_cagr
    beat = ("pass", "BEATS") if excess > 0 else ("fail", "LAGS")

    rows = [
        _row("Benchmark CAGR (equal-weight)", _pct(bench_cagr)),
        _row("Excess CAGR vs benchmark", _pct(excess), beat),
    ]
    if inp.dsr is not None:
        badge = ("pass", "SURVIVES") if inp.dsr > 0.9 else ("fail", "WEAK")
        rows.append(_row("Deflated Sharpe Ratio (P[SR>0])", f"{inp.dsr:.2f}", badge))
    if inp.shuffle is not None:
        badge = ("pass", "SURVIVES") if inp.shuffle.survives else ("fail", "DISCARD")
        rows.append(_row("Shuffle control p-value", f"{inp.shuffle.p_value:.3f}", badge))
    if inp.pbo is not None:
        badge = ("fail", "OVERFIT") if inp.pbo.overfit else ("pass", "OK")
        rows.append(_row("Prob. of backtest overfitting", f"{inp.pbo.pbo:.2f}", badge))
    if inp.trials is not None:
        rows.append(_row("Trials logged (incl. failures)", str(inp.trials)))

    ml_rows = None
    if inp.ml:
        ml_rows = [
            _row("Rank IC (mean)", f"{inp.ml['rank_ic_mean']:+.3f}"),
            _row("IC IR", f"{inp.ml['ic_ir']:+.2f}"),
            _row("Quantile spread", f"{inp.ml['quantile_spread']:+.4f}"),
        ]

    equity_svg = line_chart(
        {"strategy": inp.equity, "benchmark": inp.benchmark_equity},
        title="net equity (starts at 1.0)", baseline=1.0,
    )
    dd_svg = drawdown_chart(inp.equity)

    return render_html(
        title=f"AI Quant Lab — {inp.label}",
        subtitle=inp.subtitle,
        metrics=metrics,
        integrity_rows=rows,
        equity_svg=equity_svg,
        drawdown_svg=dd_svg,
        ml_rows=ml_rows,
        commentary=inp.commentary,
        footer="Net-of-cost is the primary curve. Benchmark = equal-weight, "
               "daily-rebalanced. Not investment advice.",
    )


def write_report(inp: ReportInputs, out_dir: str | Path, filename: str = "report.html") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    path.write_text(build_report(inp), encoding="utf-8")
    return path


# --- multi-strategy comparison (PBO / DSR live here) -----------------------


@dataclass
class StrategyRow:
    label: str
    stats: dict
    equity: pd.Series


def build_comparison_report(
    rows: list[StrategyRow], *, pbo: PBOResult, dsr: float, subtitle: str, top_n: int = 3
) -> str:
    ordered = sorted(rows, key=lambda r: r.stats["sharpe"], reverse=True)
    table = [
        f'<tr><td>{r.label}</td><td>{_pct(r.stats["cagr"])}</td>'
        f'<td>{r.stats["sharpe"]:.2f}</td><td>{r.stats["max_drawdown"]:.1%}</td>'
        f'<td>{r.stats.get("avg_turnover", float("nan")):.2f}</td></tr>'
        for r in ordered
    ]
    pbo_badge = ("fail", "OVERFIT") if pbo.overfit else ("pass", "OK")
    dsr_badge = ("pass", "SURVIVES") if dsr > 0.9 else ("fail", "WEAK")
    integrity = [
        _row(f"Prob. of backtest overfitting ({pbo.n_combinations} splits)",
             f"{pbo.pbo:.2f}", pbo_badge),
        _row("Deflated Sharpe of the best (P[SR>0])", f"{dsr:.2f}", dsr_badge),
        _row("Candidate strategies", str(len(rows))),
    ]
    equity_svg = line_chart(
        {r.label: r.equity for r in ordered[:top_n]},
        title="net equity — top strategies", baseline=1.0,
    )
    return render_comparison(
        title="AI Quant Lab — strategy comparison",
        subtitle=subtitle,
        table_rows=table,
        integrity_rows=integrity,
        equity_svg=equity_svg,
        footer="PBO asks whether picking the in-sample best generalizes; a high "
               "PBO means the ranking above is not trustworthy. Not investment advice.",
    )


def write_comparison_report(
    rows: list[StrategyRow], *, pbo: PBOResult, dsr: float, subtitle: str,
    out_dir: str | Path, filename: str = "comparison.html",
) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / filename
    path.write_text(build_comparison_report(rows, pbo=pbo, dsr=dsr, subtitle=subtitle),
                    encoding="utf-8")
    return path
