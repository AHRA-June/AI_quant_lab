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
        ("누적 수익률", _pct(s["total_return"])),
        ("연복리 수익률 (CAGR)", _pct(s["cagr"])),
        ("샤프지수", f"{s['sharpe']:.2f}"),
        ("소르티노지수", f"{s['sortino']:.2f}"),
        ("최대 낙폭 (MDD)", f"{s['max_drawdown']:.1%}"),
        ("연변동성", f"{s['ann_vol']:.1%}"),
        ("평균 회전율", f"{s.get('avg_turnover', float('nan')):.2f}"),
        ("비용 부담", f"{s.get('cost_drag', float('nan')):.2%}"),
        *inp.extra_metrics,
    ]

    # Benchmark comparison
    bench_cagr = cagr(inp.benchmark_equity)
    excess = s["cagr"] - bench_cagr
    beat = ("pass", "우위") if excess > 0 else ("fail", "열위")

    rows = [
        _row("벤치마크 수익률 (동일가중)", _pct(bench_cagr),
             desc="비교 기준이 되는 동일가중·일간 리밸런스 지수의 연복리 수익률입니다."),
        _row("벤치마크 대비 초과수익", _pct(excess), beat,
             desc="전략이 기준 지수를 이겼는지를 봅니다. 양수(우위)여야 의미가 있습니다."),
    ]
    if inp.dsr is not None:
        badge = ("pass", "통과") if inp.dsr > 0.9 else ("warn", "미약")
        rows.append(_row(
            "디플레이티드 샤프 (실력일 확률)", f"{inp.dsr:.2f}", badge,
            desc="여러 번 시도한 점을 감안해 보정한 샤프지수입니다. 우연이 아닌 실제 "
                 "실력일 확률이 0.9를 넘으면 통과로 봅니다."))
    if inp.shuffle is not None:
        badge = ("pass", "통과") if inp.shuffle.survives else ("fail", "폐기")
        rows.append(_row(
            "셔플 대조군 p값", f"{inp.shuffle.p_value:.3f}", badge,
            desc="수익률의 시간 순서를 무작위로 섞은 '가짜 전략'과 비교합니다. p값이 "
                 "0.05보다 작아야 성과가 우연이 아님(통과), 아니면 폐기입니다."))
    if inp.pbo is not None:
        badge = ("fail", "과최적화") if inp.pbo.overfit else ("pass", "양호")
        rows.append(_row(
            "과최적화 확률 (PBO)", f"{inp.pbo.pbo:.2f}", badge,
            desc="'표본 내에서 1등'인 전략이 표본 밖에서는 평균 이하로 떨어질 확률입니다. "
                 "높을수록 과최적화 위험이 큽니다."))
    if inp.trials is not None:
        rows.append(_row(
            "기록된 시도 횟수 (실패 포함)", str(inp.trials),
            desc="이 전략에 이르기까지 시도한 총 실험 수입니다. 많이 시도할수록 요행으로 "
                 "좋은 결과가 나올 위험이 커집니다."))

    ml_rows = None
    if inp.ml:
        ml_rows = [
            _row("순위 IC (평균)", f"{inp.ml['rank_ic_mean']:+.3f}",
                 desc="예측 순위와 실제 수익 순위의 상관관계입니다. 0.02~0.05면 유의미한 "
                      "시그널로 봅니다."),
            _row("IC 정보비율 (IC IR)", f"{inp.ml['ic_ir']:+.2f}",
                 desc="순위 IC의 안정성(평균÷표준편차)입니다. 높을수록 시그널이 꾸준합니다."),
            _row("분위 스프레드", f"{inp.ml['quantile_spread']:+.4f}",
                 desc="상위 그룹과 하위 그룹의 수익률 차이입니다. 클수록 예측력이 큽니다."),
        ]

    equity_svg = line_chart(
        {"전략": inp.equity, "벤치마크": inp.benchmark_equity},
        title="누적 수익 (1.0에서 시작)", baseline=1.0,
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
        footer="기준 곡선은 거래비용을 뺀 순수익입니다. 벤치마크 = 동일가중·일간 리밸런스. "
               "투자 자문이 아니며, 백테스트 결과는 미래 수익을 보장하지 않습니다.",
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
    pbo_badge = ("fail", "과최적화") if pbo.overfit else ("pass", "양호")
    dsr_badge = ("pass", "통과") if dsr > 0.9 else ("warn", "미약")
    integrity = [
        _row(f"과최적화 확률 (PBO · 분할 {pbo.n_combinations}회)",
             f"{pbo.pbo:.2f}", pbo_badge,
             desc="위 순위표에서 '1등'을 골랐을 때, 그 선택이 표본 밖에서도 통할지를 봅니다. "
                  "값이 높으면 순위표를 믿기 어렵습니다."),
        _row("최상위 전략의 디플레이티드 샤프 (실력일 확률)", f"{dsr:.2f}", dsr_badge,
             desc="여러 전략을 비교한 점을 보정한 값. 0.9를 넘으면 최상위 전략을 신뢰할 만합니다."),
        _row("후보 전략 수", str(len(rows)),
             desc="이 비교에 포함된 전략의 개수입니다."),
    ]
    equity_svg = line_chart(
        {r.label: r.equity for r in ordered[:top_n]},
        title="누적 수익 — 상위 전략", baseline=1.0,
    )
    return render_comparison(
        title="AI Quant Lab — 전략 비교",
        subtitle=subtitle,
        table_rows=table,
        integrity_rows=integrity,
        equity_svg=equity_svg,
        footer="PBO는 '표본 내 1등'이 표본 밖에서도 통하는지를 묻습니다. 값이 높으면 위 순위를 "
               "믿기 어렵습니다. 투자 자문이 아닙니다.",
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
