"""Self-contained HTML report template (F5.4).

No Jinja2 dependency — plain f-string assembly. The page is theme-aware
(light/dark via ``prefers-color-scheme``) and embeds the SVG charts inline, so a
report file is fully portable with no external assets.
"""

from __future__ import annotations

_CSS = """
:root { --bg:#ffffff; --fg:#1a1a1a; --muted:#666; --card:#f6f7f9; --line:#e3e6ea;
        --good:#16a34a; --bad:#dc2626; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0f1115; --fg:#e6e8eb; --muted:#9aa0a6; --card:#181b20; --line:#2a2f37; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; }
.wrap { max-width: 820px; margin: 0 auto; padding: 28px 20px 60px; }
h1 { font-size: 20px; margin: 0 0 2px; }
.sub { color: var(--muted); font-size: 12px; margin-bottom: 22px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:10px; }
.metric { background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:10px 12px; }
.metric .k { color:var(--muted); font-size:11px; text-transform:uppercase;
             letter-spacing:.03em; }
.metric .v { font-size:18px; font-weight:600; margin-top:2px; }
h2 { font-size:14px; margin:26px 0 10px; text-transform:uppercase;
     letter-spacing:.04em; color:var(--muted); }
.ql-chart { width:100%; height:auto; color:var(--fg); }
.panel { background:var(--card); border:1px solid var(--line); border-radius:10px;
         padding:14px 16px; }
.row { display:flex; justify-content:space-between; padding:5px 0;
       border-bottom:1px solid var(--line); }
.row:last-child { border-bottom:none; }
.badge { font-size:11px; font-weight:700; padding:2px 8px; border-radius:20px; }
.badge.pass { background:rgba(22,163,74,.15); color:var(--good); }
.badge.fail { background:rgba(220,38,38,.15); color:var(--bad); }
.commentary { font-style:italic; color:var(--fg); }
.foot { color:var(--muted); font-size:11px; margin-top:30px; }
table.scroll { display:block; overflow-x:auto; }
"""


def _metric(k: str, v: str) -> str:
    return f'<div class="metric"><div class="k">{k}</div><div class="v">{v}</div></div>'


def _row(label: str, value: str, badge: str | None = None) -> str:
    b = f' <span class="badge {badge[0]}">{badge[1]}</span>' if badge else ""
    return f'<div class="row"><span>{label}</span><span>{value}{b}</span></div>'


def render_comparison(
    *,
    title: str,
    subtitle: str,
    table_rows: list[str],
    integrity_rows: list[str],
    equity_svg: str,
    footer: str = "",
) -> str:
    """Multi-strategy comparison page: a ranked table + shared integrity panel."""
    head = ("<tr><th style='text-align:left'>Strategy</th><th>CAGR</th>"
            "<th>Sharpe</th><th>MaxDD</th><th>Turnover</th></tr>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{_CSS}
table.cmp {{ width:100%; border-collapse:collapse; }}
table.cmp th,table.cmp td {{ padding:7px 10px; border-bottom:1px solid var(--line);
  text-align:right; font-variant-numeric:tabular-nums; }}
table.cmp td:first-child,table.cmp th:first-child {{ text-align:left; }}
</style></head><body><div class="wrap">
<h1>{title}</h1><div class="sub">{subtitle}</div>
<h2>Strategies (ranked by Sharpe)</h2>
<div class="panel" style="overflow-x:auto"><table class="cmp">{head}{"".join(table_rows)}</table></div>
<h2>Selection integrity (across all strategies)</h2>
<div class="panel">{"".join(integrity_rows)}</div>
<h2>Top strategies — net equity</h2>{equity_svg}
<div class="foot">{footer}</div>
</div></body></html>"""


def render_html(
    *,
    title: str,
    subtitle: str,
    metrics: list[tuple[str, str]],
    integrity_rows: list[str],
    equity_svg: str,
    drawdown_svg: str,
    ml_rows: list[str] | None = None,
    commentary: str | None = None,
    footer: str = "",
) -> str:
    ml_section = ""
    if ml_rows:
        ml_section = f'<h2>ML signal (out-of-sample)</h2><div class="panel">{"".join(ml_rows)}</div>'
    comment_section = ""
    if commentary:
        comment_section = f'<h2>Commentary</h2><div class="panel commentary">{commentary}</div>'
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{_CSS}</style></head><body><div class="wrap">
<h1>{title}</h1><div class="sub">{subtitle}</div>
<h2>Performance (net of cost)</h2>
<div class="grid">{"".join(_metric(k, v) for k, v in metrics)}</div>
<h2>Equity vs benchmark</h2>{equity_svg}{drawdown_svg}
<h2>Research integrity</h2><div class="panel">{"".join(integrity_rows)}</div>
{ml_section}{comment_section}
<div class="foot">{footer}</div>
</div></body></html>"""
