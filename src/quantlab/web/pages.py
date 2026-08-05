"""Server-rendered dashboard HTML.

Plain f-string assembly (no template engine) with inline CSS — same self-contained
philosophy and palette as the report generator, so the dashboard opens with zero
external assets and matches the report visually. Korean copy, theme-aware.
"""

from __future__ import annotations

import html

from quantlab.web.store import RunRecord

_CSS = """
:root{--bg:#0b1326;--fg:#dae2fd;--muted:#8c909f;--muted2:#c2c6d6;--panel:#171f33;
 --panel2:#131b2e;--line:#2d3449;--primary:#adc6ff;--good:#4ade80;--bad:#ff9c92;
 --mono:ui-monospace,"JetBrains Mono","SFMono-Regular",Menlo,Consolas,monospace;}
@media (prefers-color-scheme:light){:root{--bg:#fff;--fg:#131b2e;--muted:#5b6472;
 --muted2:#3a4150;--panel:#f6f7f9;--panel2:#eef1f5;--line:#e3e6ea;--primary:#2563eb;
 --good:#16a34a;--bad:#dc2626;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:14px/1.6 -apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",Segoe UI,Roboto,sans-serif;}
.wrap{max-width:1040px;margin:0 auto;padding:28px 20px 64px}
header.top{display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap}
h1{font-size:21px;font-weight:700;margin:0;letter-spacing:-.01em}
h1 b{color:var(--primary)}
.tag{font-family:var(--mono);font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.summary{display:flex;gap:26px;flex-wrap:wrap;margin:18px 0 26px;padding:14px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.summary .k{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.summary .v{font-family:var(--mono);font-size:20px;font-weight:600}
h2{font-size:13px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin:26px 0 12px}
form.new{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap}
form.new .src-fields{display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap}
form.new label{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--muted2)}
form.new textarea{resize:vertical}
form.new select,form.new input{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 11px;font:14px var(--mono);min-width:160px}
form.new button{background:var(--primary);color:#00285d;border:0;border-radius:8px;padding:10px 18px;font-weight:700;cursor:pointer;font-size:13px}
@media (prefers-color-scheme:light){form.new button{color:#fff}}
.hint{color:var(--muted);font-size:12px;margin-top:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:15px 16px;display:flex;flex-direction:column;gap:10px}
.card .row1{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
.card .name{font-weight:700;font-size:15px;word-break:break-word}
.card .when{font-family:var(--mono);font-size:10px;color:var(--muted)}
.badge{font-family:var(--mono);font-size:10px;font-weight:700;padding:3px 10px;border-radius:999px;border:1px solid;white-space:nowrap;flex-shrink:0}
.badge.pass{color:var(--good);border-color:color-mix(in srgb,var(--good) 55%,transparent);background:color-mix(in srgb,var(--good) 13%,transparent)}
.badge.fail{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 55%,transparent);background:color-mix(in srgb,var(--bad) 13%,transparent)}
.metrics{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px 12px}
.metrics .k{font-size:10px;color:var(--muted)}
.metrics .v{font-family:var(--mono);font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
.metrics .v.neg{color:var(--bad)}
.card a.report{align-self:flex-start;color:var(--primary);text-decoration:none;font-size:13px;font-weight:600}
.card a.report:hover{text-decoration:underline}
.empty{color:var(--muted);background:var(--panel);border:1px dashed var(--line);border-radius:12px;padding:28px;text-align:center}
.foot{color:var(--muted);font-family:var(--mono);font-size:10.5px;margin-top:34px;padding-top:14px;border-top:1px solid var(--line)}
"""


def _e(s: object) -> str:
    return html.escape(str(s))


def _pct(x: float) -> str:
    return f"{x:+.1%}"


def _card(r: RunRecord) -> str:
    badge = ("pass", "통과") if r.survives else ("fail", "폐기")
    dd_neg = " neg" if r.max_drawdown < 0 else ""
    extra = f" · 유니버스 {r.universe_size}" if r.universe_size else ""
    extra += f" · {_e(r.window)}" if r.window else ""
    return f"""
<div class="card">
  <div class="row1">
    <div>
      <div class="name">{_e(r.strategy)}</div>
      <div class="when">{_e(r.source)} · 종목 {r.n_positions}개{extra} · {_e(r.created_at)}</div>
    </div>
    <span class="badge {badge[0]}">{badge[1]}</span>
  </div>
  <div class="metrics">
    <div><div class="k">연복리수익 (CAGR)</div><div class="v">{_pct(r.cagr)}</div></div>
    <div><div class="k">샤프지수</div><div class="v">{r.sharpe:.2f}</div></div>
    <div><div class="k">최대낙폭</div><div class="v{dd_neg}">{r.max_drawdown:.1%}</div></div>
  </div>
  <a class="report" href="/runs/{_e(r.id)}/report" target="_blank">리포트 보기 →</a>
</div>"""


DEFAULT_CONFIG_YAML = """alpha: "rank(returns(close, 120)) * rank(ts_mean(volume, 20) / ts_mean(volume, 60))"
universe: {market: [KOSPI], top_mktcap: 100, min_turnover: 1e7}
portfolio: {n_positions: 20, weighting: equal, rebalance: monthly}"""


def dashboard_page(records: list[RunRecord], strategies: list[str]) -> str:
    survived = sum(1 for r in records if r.survives)
    options = "".join(f'<option value="{_e(s)}">{_e(s)}</option>' for s in strategies)
    default_yaml = _e(DEFAULT_CONFIG_YAML)
    if records:
        body = f'<div class="grid">{"".join(_card(r) for r in records)}</div>'
    else:
        body = ('<div class="empty">아직 실행한 백테스트가 없습니다. '
                '위에서 전략을 골라 <b>백테스트 실행</b>을 눌러보세요.</div>')
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Quant Lab — 대시보드</title><style>{_CSS}</style></head><body><div class="wrap">
<header class="top">
  <h1>AI <b>Quant Lab</b> 대시보드</h1>
  <span class="tag">연구 무결성 우선 · 백테스트</span>
</header>
<div class="summary">
  <div><div class="k">총 실행</div><div class="v">{len(records)}</div></div>
  <div><div class="k">셔플 통과</div><div class="v" style="color:var(--primary)">{survived}</div></div>
  <div><div class="k">전략 종류</div><div class="v">{len(strategies)}</div></div>
</div>
<h2>새 백테스트</h2>
<form class="new" method="post" action="/api/runs" enctype="multipart/form-data">
  <label>데이터
    <select name="source" id="source-select">
      <option value="synthetic">합성 데이터</option>
      <option value="csv">실데이터 (CSV 업로드)</option>
    </select>
  </label>
  <div id="fields-synthetic" class="src-fields">
    <label>전략
      <select name="strategy">{options}</select>
    </label>
    <label>보유 종목 수
      <input type="number" name="n_positions" value="20" min="1" max="30">
    </label>
  </div>
  <div id="fields-csv" class="src-fields" style="display:none">
    <label>OHLCV CSV 파일
      <input type="file" name="csv" accept=".csv">
    </label>
    <label>시작일<input type="date" name="start"></label>
    <label>종료일<input type="date" name="end"></label>
    <label style="min-width:320px;flex:1">전략 설정 (DSL YAML)
      <textarea name="config_yaml" rows="4" style="font:12px var(--mono);width:100%;background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 11px">{default_yaml}</textarea>
    </label>
  </div>
  <button type="submit">백테스트 실행</button>
</form>
<div class="hint">합성 데이터는 즉시 실행됩니다(네트워크 불필요). CSV는 <b>date, open, high, low, close,
volume, Name</b> 컬럼의 long-format 파일을 올리면 실데이터로 동일 파이프라인이 돕니다. 모든 실행은
실패 포함 자동 기록되고, 셔플 대조군과 비교해 <b>통과/폐기</b>가 판정됩니다.</div>
<script>
(function(){{
  var sel=document.getElementById('source-select');
  var syn=document.getElementById('fields-synthetic');
  var csv=document.getElementById('fields-csv');
  function upd(){{ var c=sel.value==='csv'; syn.style.display=c?'none':''; csv.style.display=c?'':'none'; }}
  sel.addEventListener('change', upd); upd();
}})();
</script>
<h2>최근 실행</h2>
{body}
<div class="foot">AI Quant Lab · 백테스트 결과는 미래 수익을 보장하지 않습니다. 투자 자문이 아닙니다.</div>
</div></body></html>"""
