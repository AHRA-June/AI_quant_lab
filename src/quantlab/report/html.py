"""Self-contained HTML report template (F5.4).

No Jinja2 dependency — plain f-string assembly. The page is theme-aware
(light/dark via ``prefers-color-scheme``) and embeds the SVG charts inline, so a
report file is fully portable with no external assets.

The visual language (deep-navy surfaces, a cool primary, mono-spaced numerals and
bordered verdict pills) is carried entirely by inline CSS — no CDN, no web fonts,
no icon packs — so the "opens offline with zero network" property (part of the
reproducibility bundle) is preserved.

User-facing copy is Korean, and jargon-heavy rows (integrity, ML) carry a short
plain-language description so the report reads as an explanation, not a cipher.
"""

from __future__ import annotations

# Numerals use a monospaced stack for tabular alignment; it degrades from
# JetBrains Mono (if the viewer happens to have it) down to the platform mono
# font. No font is *fetched* — the report stays self-contained.
_MONO = ('ui-monospace,"JetBrains Mono","SFMono-Regular",Menlo,Consolas,'
         '"Liberation Mono",monospace')

_CSS = f"""
:root {{
  --bg:#0b1326; --fg:#dae2fd; --muted:#8c909f; --muted2:#c2c6d6;
  --panel:#171f33; --panel2:#131b2e; --line:#2d3449; --primary:#adc6ff;
  --good:#4ade80; --bad:#ff9c92; --warn:#ffb786;
  --mono:{_MONO};
}}
@media (prefers-color-scheme: light) {{
  :root {{
    --bg:#ffffff; --fg:#131b2e; --muted:#5b6472; --muted2:#3a4150;
    --panel:#f6f7f9; --panel2:#eef1f5; --line:#e3e6ea; --primary:#2563eb;
    --good:#16a34a; --bad:#dc2626; --warn:#b45309;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg);
        font:14px/1.6 -apple-system,"Apple SD Gothic Neo","Malgun Gothic",
        "Noto Sans KR",Segoe UI,Roboto,sans-serif;
        -webkit-font-smoothing:antialiased; }}
.wrap {{ max-width: 880px; margin: 0 auto; padding: 30px 20px 64px; }}
h1 {{ font-size: 21px; font-weight:700; margin: 0 0 4px; letter-spacing:-0.01em; }}
h1 .lab {{ color:var(--primary); }}
.sub {{ color: var(--muted); font-family:var(--mono); font-size: 11px;
        letter-spacing:.03em; margin-bottom: 10px; }}
.intro {{ color:var(--muted2); font-size:13px; line-height:1.7;
          background:var(--panel); border:1px solid var(--line);
          border-radius:12px; padding:12px 15px; margin-bottom:8px; }}
h2 {{ font-size:14.5px; font-weight:700; margin:30px 0 3px; color:var(--fg);
      display:flex; align-items:center; gap:8px; }}
h2 .ico {{ color:var(--primary); }}
.sectiondesc {{ color:var(--muted); font-size:12px; line-height:1.6; margin:0 0 12px; }}

/* performance profile — two-column stat grid with rules */
.stats {{ display:grid; grid-template-columns:1fr 1fr; gap:0 32px; }}
.stat {{ display:flex; align-items:baseline; justify-content:space-between; gap:12px;
         padding:10px 2px; border-bottom:1px solid var(--line); min-width:0; }}
.stat .k {{ color:var(--muted2); font-size:13px; white-space:nowrap; }}
.stat .v {{ font-family:var(--mono); font-weight:600; font-size:15px;
            font-variant-numeric:tabular-nums; text-align:right; }}
.stat .v.neg {{ color:var(--bad); }}
@media (max-width:560px) {{ .stats {{ grid-template-columns:1fr; gap:0; }} }}

.ql-chart {{ width:100%; height:auto; color:var(--fg);
             background:var(--panel2); border:1px solid var(--line);
             border-radius:12px; padding:6px; margin-bottom:6px; }}

.panel {{ background:var(--panel); border:1px solid var(--line);
          border-radius:12px; padding:2px 16px; }}
.row {{ display:flex; flex-direction:column; gap:3px;
        padding:12px 0; border-bottom:1px solid var(--line); }}
.row:last-child {{ border-bottom:none; }}
.rowtop {{ display:flex; justify-content:space-between; align-items:center; gap:12px; }}
.row .lab {{ color:var(--fg); font-weight:600; font-size:13.5px; min-width:0; }}
.row .val {{ font-family:var(--mono); font-variant-numeric:tabular-nums;
             display:inline-flex; align-items:center; gap:10px; white-space:nowrap; }}
.row .desc {{ color:var(--muted); font-size:12px; line-height:1.55; padding-right:80px; }}
@media (max-width:560px) {{ .row .desc {{ padding-right:0; }} }}

.badge {{ font-family:var(--mono); font-size:11px; font-weight:700;
          letter-spacing:.02em; padding:3px 11px; border-radius:999px;
          border:1px solid; white-space:nowrap; }}
.badge.pass {{ color:var(--good); border-color:color-mix(in srgb,var(--good) 55%,transparent);
               background:color-mix(in srgb,var(--good) 13%,transparent); }}
.badge.fail {{ color:var(--bad); border-color:color-mix(in srgb,var(--bad) 55%,transparent);
               background:color-mix(in srgb,var(--bad) 13%,transparent); }}
.badge.warn {{ color:var(--warn); border-color:color-mix(in srgb,var(--warn) 55%,transparent);
               background:color-mix(in srgb,var(--warn) 13%,transparent); }}

.commentary {{ border-left:3px solid var(--primary); background:var(--panel);
               border-radius:0 12px 12px 0; padding:14px 16px; color:var(--muted2);
               line-height:1.7; }}
.foot {{ color:var(--muted); font-size:11.5px; line-height:1.6;
         margin-top:34px; padding-top:14px; border-top:1px solid var(--line); }}
"""

# Inline shield glyph for the integrity section — no icon-font dependency.
_SHIELD = ('<svg class="ico" viewBox="0 0 24 24" width="16" height="16" fill="none" '
           'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
           'stroke-linejoin="round" aria-hidden="true">'
           '<path d="M12 2l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V5l7-3z"/></svg>')


def _metric(k: str, v: str) -> str:
    neg = " neg" if v.strip().startswith("-") else ""
    return f'<div class="stat"><span class="k">{k}</span><span class="v{neg}">{v}</span></div>'


def _row(label: str, value: str, badge: tuple[str, str] | None = None,
         desc: str | None = None) -> str:
    b = f' <span class="badge {badge[0]}">{badge[1]}</span>' if badge else ""
    d = f'<div class="desc">{desc}</div>' if desc else ""
    return (f'<div class="row"><div class="rowtop">'
            f'<span class="lab">{label}</span>'
            f'<span class="val">{value}{b}</span></div>{d}</div>')


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
    head = ("<tr><th style='text-align:left'>전략</th><th>연복리수익</th>"
            "<th>샤프</th><th>최대낙폭</th><th>회전율</th></tr>")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{_CSS}
table.cmp {{ width:100%; border-collapse:collapse; }}
table.cmp td {{ font-family:var(--mono); }}
table.cmp th,table.cmp td {{ padding:9px 10px; border-bottom:1px solid var(--line);
  text-align:right; font-variant-numeric:tabular-nums; }}
table.cmp th {{ color:var(--muted); font-size:12px; font-weight:700; }}
table.cmp td:first-child,table.cmp th:first-child {{ text-align:left; }}
</style></head><body><div class="wrap">
<h1>{title}</h1><div class="sub">{subtitle}</div>
<h2>전략 순위 <span style="color:var(--muted);font-weight:500;font-size:12px">(샤프지수 기준 정렬)</span></h2>
<div class="sectiondesc">여러 후보 전략을 나란히 비교합니다. 표본 외 성능이 좋은 전략이 위로 옵니다.</div>
<div class="panel" style="overflow-x:auto"><table class="cmp">{head}{"".join(table_rows)}</table></div>
<h2>{_SHIELD}선택 무결성 <span style="color:var(--muted);font-weight:500;font-size:12px">(전체 전략 대상)</span></h2>
<div class="sectiondesc">여러 전략 중 '가장 좋아 보이는 것'을 고르는 행위 자체가 요행을 부릅니다. 그 위험을 아래에서 측정합니다.</div>
<div class="panel">{"".join(integrity_rows)}</div>
<h2>상위 전략 — 누적 수익</h2>{equity_svg}
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
        ml_section = (
            '<h2>머신러닝 시그널 '
            '<span style="color:var(--muted);font-weight:500;font-size:12px">(표본 외)</span></h2>'
            '<div class="sectiondesc">순위 예측 모델이 만든 시그널을, 학습에 쓰지 않은 기간에서 '
            '평가한 성능입니다.</div>'
            f'<div class="panel">{"".join(ml_rows)}</div>'
        )
    comment_section = ""
    if commentary:
        comment_section = (
            '<h2>해설</h2>'
            '<div class="sectiondesc">위 수치와 무결성 판정을 근거로 한 자동 해설입니다.</div>'
            f'<div class="commentary">{commentary}</div>'
        )
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{_CSS}</style></head><body><div class="wrap">
<h1>{title}</h1><div class="sub">{subtitle}</div>
<div class="intro">이 리포트는 전략을 <b>정직하게</b> 평가하기 위해, 얼마나 벌었는지(성과)와
함께 <b>그 결과를 얼마나 믿을 수 있는지</b>(무결성)를 같이 보여줍니다. 모든 성과는
거래비용·슬리피지·다음날(t+1) 체결을 반영한 순수익 기준입니다.</div>
<h2>성과 요약 <span style="color:var(--muted);font-weight:500;font-size:12px">(거래비용 차감 후)</span></h2>
<div class="sectiondesc">전략을 실제로 운용했다면 어떤 성과였는지를 요약합니다.</div>
<div class="stats">{"".join(_metric(k, v) for k, v in metrics)}</div>
<h2>누적 수익 곡선 <span style="color:var(--muted);font-weight:500;font-size:12px">(벤치마크 대비)</span></h2>
<div class="sectiondesc">1.0에서 시작한 누적 수익입니다. 파란선이 전략, 회색선이 벤치마크(동일가중 지수).
아래 그래프는 최고점 대비 얼마나 하락했는지(낙폭)를 보여줍니다.</div>
{equity_svg}{drawdown_svg}
<h2>{_SHIELD}연구 무결성 검증</h2>
<div class="sectiondesc">가장 큰 위험은 버그가 아니라, 여러 전략을 돌리다 우연히 좋아 보이는 걸
진짜라고 믿는 <b>자기기만</b>입니다. 아래 지표들이 그 요행과 과최적화를 걸러냅니다.</div>
<div class="panel">{"".join(integrity_rows)}</div>
{ml_section}{comment_section}
<div class="foot">{footer}</div>
</div></body></html>"""
