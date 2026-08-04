"""Reporting (M4): charts, HTML assembly, benchmark, commentary."""

import numpy as np
import pandas as pd

from quantlab.dsl.llm import LLMClient
from quantlab.integrity.pbo import PBOResult
from quantlab.integrity.shuffle import ShuffleResult
from quantlab.report.charts import drawdown_chart, line_chart
from quantlab.report.commentary import generate_commentary
from quantlab.report.report import ReportInputs, build_report, equal_weight_benchmark, write_report


def _equity(seed=0, drift=0.001):
    idx = pd.bdate_range("2022-01-01", periods=120)
    rng = np.random.default_rng(seed)
    return (1 + pd.Series(drift + rng.normal(0, 0.01, 120), index=idx)).cumprod()


def _stats():
    return {
        "total_return": 0.25, "cagr": 0.18, "ann_vol": 0.12, "sharpe": 1.5,
        "sortino": 1.8, "max_drawdown": -0.08, "win_rate": 0.55,
        "avg_turnover": 0.1, "cost_drag": 0.03,
    }


# --- charts ----------------------------------------------------------------


def test_line_chart_has_polyline_per_series():
    svg = line_chart({"a": _equity(0), "b": _equity(1)}, baseline=1.0)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert svg.count("<polyline") == 2  # one per series


def test_drawdown_chart_renders():
    svg = drawdown_chart(_equity(0))
    assert "<polygon" in svg and "drawdown" in svg


def test_line_chart_handles_empty():
    svg = line_chart({"a": pd.Series(dtype=float)})
    assert "<svg" in svg  # degrades gracefully


# --- benchmark -------------------------------------------------------------


def test_equal_weight_benchmark_matches_mean_returns():
    idx = pd.bdate_range("2022-01-01", periods=30)
    rets = pd.DataFrame(np.random.default_rng(0).normal(0, 0.01, (30, 5)), index=idx)
    bench = equal_weight_benchmark(rets)
    expected = (1 + rets.mean(axis=1)).cumprod()
    assert np.allclose(bench.values, expected.values)


# --- report assembly -------------------------------------------------------


def _inputs(**kw):
    base = dict(
        label="test_strategy", subtitle="synthetic",
        stats=_stats(), equity=_equity(0, 0.001),
        benchmark_equity=_equity(1, 0.0002),
    )
    base.update(kw)
    return ReportInputs(**base)


def test_report_contains_sections_and_values():
    html = build_report(_inputs(trials=7))
    assert "AI Quant Lab — test_strategy" in html
    assert "Research integrity" in html and "Equity vs benchmark" in html
    assert "+18.0%" in html  # CAGR rendered
    assert "Trials logged" in html and ">7<" in html
    assert html.count("<polyline") >= 2  # strategy + benchmark


def test_report_flags_failed_integrity():
    shuf = ShuffleResult(observed=0.0, p_value=0.4, null_mean=0.0, null_std=0.01, n_shuffles=50)
    pbo = PBOResult(pbo=0.7, logits=np.array([-1.0, -0.5]), n_combinations=2)
    html = build_report(_inputs(shuffle=shuf, pbo=pbo, dsr=0.6))
    assert "DISCARD" in html and "OVERFIT" in html and "WEAK" in html
    assert "badge fail" in html


def test_report_marks_benchmark_beat():
    html = build_report(_inputs())  # strategy drift 0.001 > benchmark 0.0002
    assert "BEATS" in html


def test_write_report_creates_file(tmp_path):
    path = write_report(_inputs(), tmp_path / "exp1")
    assert path.exists() and path.suffix == ".html"
    assert "<!doctype html>" in path.read_text().lower()


# --- LLM commentary --------------------------------------------------------


class FixedClient:
    def __init__(self, text): self.text = text; self.last_user = None
    def complete(self, system, user): self.last_user = user; return self.text


def test_commentary_uses_client_and_passes_facts():
    client = FixedClient("The high Sharpe is not trustworthy: the shuffle control discards it.")
    shuf = ShuffleResult(observed=0.0, p_value=0.4, null_mean=0.0, null_std=0.01, n_shuffles=50)
    text = generate_commentary(client, _inputs(shuffle=shuf))
    assert "not trustworthy" in text
    assert "DISCARD" in client.last_user  # integrity verdict handed to the model
    assert isinstance(client, LLMClient)
