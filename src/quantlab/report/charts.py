"""Dependency-free inline SVG charts (F5.3).

Hand-drawn SVG keeps reports fully self-contained (no matplotlib/plotly, no
external assets) and theme-aware — strokes use an explicit palette while the
surrounding report CSS adapts the background. Charts scale with ``viewBox`` so
they stay crisp at any width.
"""

from __future__ import annotations

import pandas as pd

# Categorical strokes. Index 0/1 are tuned for the flagship report where the two
# series are (strategy, benchmark): a cool primary against a neutral grey, matching
# the report surface palette. The rest stay colorblind-safe for comparison overlays.
_PALETTE = ["#adc6ff", "#8c909f", "#4ade80", "#ffb786", "#c58bff"]
_DRAWDOWN = "#ffb4ab"
_PAD = 36


def _points(values: list[float], lo: float, hi: float, w: int, h: int) -> str:
    n = len(values)
    span = (hi - lo) or 1.0
    xs = [_PAD + (w - 2 * _PAD) * (i / max(n - 1, 1)) for i in range(n)]
    ys = [h - _PAD - (h - 2 * _PAD) * ((v - lo) / span) for v in values]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))


def line_chart(series: dict[str, pd.Series], *, width: int = 720, height: int = 280,
               title: str = "", baseline: float | None = None) -> str:
    """Multi-series line chart. All series are plotted on a shared y-scale."""
    clean = {k: v.dropna() for k, v in series.items() if len(v.dropna())}
    if not clean:
        return f'<svg viewBox="0 0 {width} {height}"><text x="{_PAD}" y="{_PAD}">no data</text></svg>'

    lo = min(s.min() for s in clean.values())
    hi = max(s.max() for s in clean.values())
    if baseline is not None:
        lo, hi = min(lo, baseline), max(hi, baseline)

    parts = [f'<svg viewBox="0 0 {width} {height}" class="ql-chart" '
             f'role="img" aria-label="{title}">']
    # frame + faint horizontal gridlines
    parts.append(f'<rect x="{_PAD}" y="{_PAD}" width="{width - 2 * _PAD}" '
                 f'height="{height - 2 * _PAD}" fill="none" stroke="currentColor" '
                 f'stroke-opacity="0.15"/>')
    for g in (0.25, 0.5, 0.75):
        gy = _PAD + (height - 2 * _PAD) * g
        parts.append(f'<line x1="{_PAD}" y1="{gy:.1f}" x2="{width - _PAD}" y2="{gy:.1f}" '
                     f'stroke="currentColor" stroke-opacity="0.07"/>')
    if baseline is not None and lo <= baseline <= hi:
        by = height - _PAD - (height - 2 * _PAD) * ((baseline - lo) / ((hi - lo) or 1))
        parts.append(f'<line x1="{_PAD}" y1="{by:.1f}" x2="{width - _PAD}" y2="{by:.1f}" '
                     f'stroke="currentColor" stroke-opacity="0.3" stroke-dasharray="4 3"/>')
    # series
    legend = []
    for i, (label, s) in enumerate(clean.items()):
        color = _PALETTE[i % len(_PALETTE)]
        pts = _points(list(s.to_numpy(dtype=float)), lo, hi, width, height)
        parts.append(f'<polyline points="{pts}" fill="none" stroke="{color}" '
                     f'stroke-width="2"/>')
        lx = _PAD + 8 + i * 150
        legend.append(f'<rect x="{lx}" y="8" width="10" height="10" fill="{color}"/>'
                      f'<text x="{lx + 14}" y="17" font-size="12" '
                      f'fill="currentColor">{label}</text>')
    parts.extend(legend)
    if title:
        parts.append(f'<text x="{_PAD}" y="{height - 8}" font-size="12" '
                     f'fill="currentColor" fill-opacity="0.7">{title}</text>')
    # y-axis min/max labels
    parts.append(f'<text x="4" y="{_PAD + 4}" font-size="10" fill="currentColor" '
                 f'fill-opacity="0.6">{hi:.2f}</text>')
    parts.append(f'<text x="4" y="{height - _PAD}" font-size="10" fill="currentColor" '
                 f'fill-opacity="0.6">{lo:.2f}</text>')
    parts.append("</svg>")
    return "".join(parts)


def drawdown_chart(equity: pd.Series, *, width: int = 720, height: int = 180) -> str:
    """Filled drawdown (peak-to-trough, ≤ 0) area chart."""
    eq = equity.dropna()
    dd = (eq / eq.cummax() - 1.0) * 100  # percent
    lo, hi = min(dd.min(), 0.0), 0.0
    pts = _points(list(dd.to_numpy(dtype=float)), lo, hi, width, height)
    zero_y = height - _PAD - (height - 2 * _PAD) * ((0 - lo) / ((hi - lo) or 1))
    area = f"{_PAD},{zero_y:.1f} " + pts + f" {width - _PAD},{zero_y:.1f}"
    return (
        f'<svg viewBox="0 0 {width} {height}" class="ql-chart" role="img" '
        f'aria-label="drawdown">'
        f'<polygon points="{area}" fill="{_DRAWDOWN}" fill-opacity="0.20"/>'
        f'<polyline points="{pts}" fill="none" stroke="{_DRAWDOWN}" stroke-width="1.5"/>'
        f'<text x="4" y="{height - _PAD}" font-size="10" fill="currentColor" '
        f'fill-opacity="0.6">{lo:.1f}%</text>'
        f'<text x="{_PAD}" y="{height - 8}" font-size="12" fill="currentColor" '
        f'fill-opacity="0.7">낙폭 (%)</text></svg>'
    )
