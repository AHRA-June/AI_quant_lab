"""Server-rendered dashboard HTML (dashboard · compare · integrity audit).

Plain f-string assembly (no template engine) with inline CSS — same self-contained
philosophy and palette as the report generator, so the pages open with zero
external assets and match the report visually. Korean copy, theme-aware.
"""

from __future__ import annotations

import html

from quantlab.web.store import RunRecord

_CSS = """
:root{--bg:#0b1326;--fg:#dae2fd;--muted:#8c909f;--muted2:#c2c6d6;--panel:#171f33;
 --panel2:#131b2e;--line:#2d3449;--primary:#adc6ff;--good:#4ade80;--bad:#ff9c92;--warn:#ffb786;
 --mono:ui-monospace,"JetBrains Mono","SFMono-Regular",Menlo,Consolas,monospace;}
@media (prefers-color-scheme:light){:root{--bg:#fff;--fg:#131b2e;--muted:#5b6472;
 --muted2:#3a4150;--panel:#f6f7f9;--panel2:#eef1f5;--line:#e3e6ea;--primary:#2563eb;
 --good:#16a34a;--bad:#dc2626;--warn:#b45309;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font:14px/1.6 -apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",Segoe UI,Roboto,sans-serif;}
.wrap{max-width:1040px;margin:0 auto;padding:24px 20px 64px}
header.top{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
h1{font-size:20px;font-weight:700;margin:0;letter-spacing:-.01em}
h1 b{color:var(--primary)}
nav{display:flex;gap:6px}
nav a{text-decoration:none;color:var(--muted2);font-size:13px;font-weight:600;padding:7px 13px;border-radius:8px;border:1px solid transparent}
nav a:hover{background:var(--panel)}
nav a.active{color:var(--primary);border-color:var(--line);background:var(--panel)}
.summary{display:flex;gap:26px;flex-wrap:wrap;margin:18px 0 26px;padding:14px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.summary .k{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.summary .v{font-family:var(--mono);font-size:20px;font-weight:600}
h2{font-size:13px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin:26px 0 12px}
.desc{color:var(--muted);font-size:12px;margin:-6px 0 12px}
form.new{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap}
form.new .src-fields{display:flex;gap:14px;align-items:flex-end;flex-wrap:wrap}
form.new label{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--muted2)}
form.new textarea{resize:vertical}
form.new select,form.new input{background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 11px;font:14px var(--mono);min-width:160px}
button.go{background:var(--primary);color:#00285d;border:0;border-radius:8px;padding:10px 18px;font-weight:700;cursor:pointer;font-size:13px}
@media (prefers-color-scheme:light){button.go{color:#fff}}
.hint{color:var(--muted);font-size:12px;margin-top:8px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:15px 16px;display:flex;flex-direction:column;gap:10px}
.card .row1{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
.card .name{font-weight:700;font-size:15px;word-break:break-word}
.card .when{font-family:var(--mono);font-size:10px;color:var(--muted)}
.badge{font-family:var(--mono);font-size:10px;font-weight:700;padding:3px 10px;border-radius:999px;border:1px solid;white-space:nowrap;flex-shrink:0}
.badge.pass{color:var(--good);border-color:color-mix(in srgb,var(--good) 55%,transparent);background:color-mix(in srgb,var(--good) 13%,transparent)}
.badge.fail{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 55%,transparent);background:color-mix(in srgb,var(--bad) 13%,transparent)}
.badge.warn{color:var(--warn);border-color:color-mix(in srgb,var(--warn) 55%,transparent);background:color-mix(in srgb,var(--warn) 13%,transparent)}
.metrics{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px 12px}
.metrics .k{font-size:10px;color:var(--muted)}
.metrics .v{font-family:var(--mono);font-size:15px;font-weight:600;font-variant-numeric:tabular-nums}
.metrics .v.neg{color:var(--bad)}
.card .name a{color:var(--fg);text-decoration:none}
.card .name a:hover{color:var(--primary);text-decoration:underline}
.card a.report{align-self:flex-start;color:var(--primary);text-decoration:none;font-size:13px;font-weight:600}
.card a.report:hover{text-decoration:underline}
form.inline{display:inline;margin:0}
button.link{background:none;border:0;color:var(--primary);font:inherit;font-size:12px;cursor:pointer;padding:0;text-decoration:underline}
button.danger{background:none;border:1px solid color-mix(in srgb,var(--bad) 55%,transparent);color:var(--bad);border-radius:8px;padding:8px 14px;font-weight:600;cursor:pointer;font-size:13px}
.detailmeta{display:flex;gap:26px;flex-wrap:wrap;margin:14px 0}
.detailmeta .k{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.detailmeta .v{font-family:var(--mono);font-size:15px;font-weight:600}
.actions{display:flex;gap:10px;align-items:center;margin:8px 0 4px}
iframe.report{width:100%;height:78vh;border:1px solid var(--line);border-radius:12px;background:#fff}
.dsl{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:6px 0 2px}
.dsl span{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.dsl code,code{font-family:var(--mono);font-size:12.5px;background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:3px 8px;color:var(--primary)}
.empty{color:var(--muted);background:var(--panel);border:1px dashed var(--line);border-radius:12px;padding:28px;text-align:center}
.jobs{display:flex;flex-direction:column;gap:8px}
.job{display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.job .jobname{font-weight:600;font-size:14px}
.job .jobkind{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.job .joberr{flex-basis:100%;font-family:var(--mono);font-size:11px;color:var(--bad)}
table.tbl{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
table.tbl th,table.tbl td{padding:10px 12px;text-align:right;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
table.tbl td:not(:first-child){font-family:var(--mono)}
table.tbl th{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.05em;font-weight:700}
table.tbl th:first-child,table.tbl td:first-child{text-align:left}
table.tbl tr:last-child td{border-bottom:none}
tr.dim td{opacity:.45}
.pbocard{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:18px;display:flex;flex-wrap:wrap;gap:26px;align-items:center}
.pbocard .big{font-family:var(--mono);font-size:34px;font-weight:700;line-height:1}
.pbocard .k{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
.pbocard .v{font-family:var(--mono);font-size:18px;font-weight:600}
.banner{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:8px;padding:12px 15px;color:var(--muted2);font-size:13px}
.foot{color:var(--muted);font-family:var(--mono);font-size:10.5px;margin-top:34px;padding-top:14px;border-top:1px solid var(--line)}
form.new .fld{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--muted2)}
.datefield{position:relative;display:inline-block}
.datefield .dfin{cursor:pointer;min-width:150px}
.cal{position:absolute;z-index:60;top:calc(100% + 5px);left:0;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px;box-shadow:0 10px 30px rgba(0,0,0,.30)}
.calhd{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;font-weight:700;font-size:13px;gap:8px}
.calhd button{background:var(--panel2);border:1px solid var(--line);color:var(--fg);border-radius:6px;width:28px;height:28px;cursor:pointer;font-size:15px;min-width:0;padding:0;line-height:1}
.calgrid{display:grid;grid-template-columns:repeat(7,32px);gap:2px}
.calgrid .cw{font-size:11px;color:var(--muted);text-align:center;padding:2px 0}
.calgrid .cd{background:none;border:0;color:var(--fg);border-radius:6px;height:30px;cursor:pointer;font:13px var(--mono);padding:0;min-width:0}
.calgrid .cd:hover{background:var(--panel2)}
.calgrid .cd.sel{background:var(--primary);color:#00285d}
@media (prefers-color-scheme:light){.calgrid .cd.sel{color:#fff}}
.frow{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-end;width:100%}
details.adv{width:100%;margin-top:2px}
details.adv summary{cursor:pointer;color:var(--primary);font-size:13px;user-select:none}
details.adv textarea{margin-top:8px}
.presetdesc{color:var(--muted2);font-size:12.5px;width:100%;margin-top:-4px}
"""

DEFAULT_CONFIG_YAML = """alpha: "rank(returns(close, 120)) * rank(ts_mean(volume, 20) / ts_mean(volume, 60))"
universe: {market: [KOSPI], top_mktcap: 100, min_turnover: 1e7}
portfolio: {n_positions: 20, weighting: equal, rebalance: monthly}"""

# Self-contained pop-up calendar (no native <input type=date>, no external libs).
# Every element with class "datefield" and a data-name attr becomes a day-picker
# that writes YYYY-MM-DD into a hidden input of that name (what the backend parses).
_CAL_JS = r"""
function qcal(host){
  var name=host.getAttribute('data-name');
  var hidden=document.createElement('input'); hidden.type='hidden'; hidden.name=name;
  var text=document.createElement('input'); text.type='text'; text.readOnly=true;
  text.className='dfin'; text.placeholder='YYYY-MM-DD'; text.autocomplete='off';
  var pop=document.createElement('div'); pop.className='cal'; pop.style.display='none';
  host.appendChild(hidden); host.appendChild(text); host.appendChild(pop);
  var view=new Date(); view.setDate(1); var sel=null;
  function pad(n){return String(n).padStart(2,'0');}
  var dd=host.getAttribute('data-default');
  if(dd!==null && dd!==''){
    var b=new Date(); b.setHours(0,0,0,0); b.setDate(b.getDate()+parseInt(dd,10));
    sel=b.getFullYear()+'-'+pad(b.getMonth()+1)+'-'+pad(b.getDate());
    hidden.value=sel; text.value=sel;
  }
  function render(){
    var y=view.getFullYear(), m=view.getMonth();
    var start=new Date(y,m,1).getDay(), days=new Date(y,m+1,0).getDate();
    var h='<div class="calhd"><button type="button" data-nav="-1">‹</button>'
         +'<span>'+y+'년 '+(m+1)+'월</span>'
         +'<button type="button" data-nav="1">›</button></div><div class="calgrid">';
    ['일','월','화','수','목','금','토'].forEach(function(w){h+='<span class="cw">'+w+'</span>';});
    for(var i=0;i<start;i++) h+='<span></span>';
    for(var d=1;d<=days;d++){var iso=y+'-'+pad(m+1)+'-'+pad(d);
      h+='<button type="button" class="cd'+(sel===iso?' sel':'')+'" data-iso="'+iso+'">'+d+'</button>';}
    pop.innerHTML=h+'</div>';
  }
  function open(){pop.style.display='block'; if(sel){view=new Date(sel+'T00:00:00'); view.setDate(1);} render();}
  text.addEventListener('click',function(e){
    e.preventDefault(); e.stopPropagation();
    if(pop.style.display==='none') open(); else pop.style.display='none';
  });
  // click delegation on the popup. preventDefault/stopPropagation so a wrapping
  // element (or the document handler) can't swallow the nav/day click.
  pop.addEventListener('click',function(e){
    e.preventDefault(); e.stopPropagation();
    var t=e.target.closest ? e.target.closest('button') : e.target;
    if(!t) return;
    var nav=t.getAttribute('data-nav');
    if(nav){view.setMonth(view.getMonth()+parseInt(nav,10)); render(); return;}
    var iso=t.getAttribute('data-iso');
    if(iso){sel=iso; hidden.value=iso; text.value=iso; pop.style.display='none';}
  });
  document.addEventListener('click',function(e){if(!host.contains(e.target)) pop.style.display='none';});
}
document.querySelectorAll('.datefield').forEach(qcal);
"""


def _datefield(name: str, caption: str, default_days: int | None = None) -> str:
    """A captioned day-picker field. Deliberately **not** wrapped in a <label>:
    a <label> forwards clicks to its control, which would swallow the calendar's
    prev/next and day-cell clicks (popup closes before the click registers).

    ``default_days`` pre-fills the field to ``today + default_days`` (e.g. -365 for
    "a year ago") so users start from a valid past window instead of empty inputs.
    """
    dd = f' data-default="{int(default_days)}"' if default_days is not None else ""
    return (f'<div class="fld"><span>{_e(caption)}</span>'
            f'<span class="datefield" data-name="{_e(name)}"{dd}></span></div>')


def _e(s: object) -> str:
    return html.escape(str(s))


def _pct(x: float) -> str:
    try:
        return f"{x:+.1%}"
    except (TypeError, ValueError):
        return "—"


def _num(x, fmt: str = ".2f") -> str:
    try:
        return format(float(x), fmt)
    except (TypeError, ValueError):
        return "—"


def _nav(active: str) -> str:
    items = [("/", "대시보드", "dashboard"), ("/screen", "종목 찾기", "screen"),
             ("/compare", "비교", "compare"), ("/audit", "무결성 감사", "audit")]
    links = "".join(
        f'<a href="{href}" class="{"active" if key == active else ""}">{label}</a>'
        for href, label, key in items
    )
    return f"<nav>{links}</nav>"


def _shell(title: str, active: str, inner: str, refresh: int | None = None) -> str:
    meta_refresh = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">{meta_refresh}
<title>AI Quant Lab — {_e(title)}</title><style>{_CSS}</style></head><body><div class="wrap">
<header class="top"><h1>AI <b>Quant Lab</b></h1>{_nav(active)}</header>
{inner}
<div class="foot">AI Quant Lab · 백테스트 결과는 미래 수익을 보장하지 않습니다. 투자 자문이 아닙니다.</div>
</div></body></html>"""


_JOB_BADGE = {"queued": ("warn", "대기"), "running": ("warn", "실행 중"),
              "done": ("pass", "완료"), "failed": ("fail", "실패"),
              "cancelled": ("fail", "취소됨")}


def _jobs_section(jobs: list) -> str:
    """Active + recently-terminal (failed/cancelled) jobs. Done jobs drop off."""
    show = [j for j in jobs if j.status in ("queued", "running", "failed", "cancelled")][:8]
    if not show:
        return ""
    items = ""
    for j in show:
        cls, label = _JOB_BADGE.get(j.status, ("warn", j.status))
        err = f'<div class="joberr">{_e(j.error)}</div>' if j.error else ""
        cancel = (f'<form method="post" action="/api/jobs/{_e(j.id)}/cancel" class="inline">'
                  f'<button class="link" type="submit">취소</button></form>'
                  if j.status == "queued" else "")
        items += (f'<div class="job"><span class="badge {cls}">{label}</span>'
                  f'<span class="jobname">{_e(j.label)}</span>'
                  f'<span class="jobkind">{_e(j.kind)}</span>'
                  f'<span style="margin-left:auto">{cancel}</span>{err}</div>')
    return f'<h2>실행 중 작업</h2><div class="jobs">{items}</div>'


# --- dashboard -------------------------------------------------------------


def _card(r: RunRecord) -> str:
    badge = ("pass", "통과") if r.survives else ("fail", "폐기")
    dd_neg = " neg" if r.max_drawdown < 0 else ""
    extra = f" · 유니버스 {r.universe_size}" if r.universe_size else ""
    extra += f" · {_e(r.window)}" if r.window else ""
    return f"""
<div class="card">
  <div class="row1">
    <div>
      <div class="name"><a href="/runs/{_e(r.id)}">{_e(r.strategy)}</a></div>
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


def dashboard_page(records: list[RunRecord], strategies: list[str], jobs: list | None = None,
                   llm_available: bool = False, krx_available: bool = False) -> str:
    jobs = jobs or []
    survived = sum(1 for r in records if r.survives)
    options = "".join(f'<option value="{_e(s)}">{_e(s)}</option>' for s in strategies)
    default_yaml = _e(DEFAULT_CONFIG_YAML)
    from quantlab.web.service import DEFAULT_KRX_TICKERS  # lazy: avoid import cycle
    krx_default_tickers = _e(", ".join(DEFAULT_KRX_TICKERS))
    jobs_html = _jobs_section(jobs)
    active = any(getattr(j, "active", False) for j in jobs)
    nl_option = ('<option value="nl">자연어 아이디어 (LLM)</option>' if llm_available
                 else '<option value="nl" disabled>자연어 아이디어 (LLM 미설정)</option>')
    krx_option = ('<option value="krx">실데이터 (KRX 일봉)</option>' if krx_available
                  else '<option value="krx" disabled>실데이터 (KRX — pykrx 미설치)</option>')
    notes = []
    if not llm_available:
        notes.append("자연어 입력: <b>ANTHROPIC_API_KEY</b> 설정 + <code>pip install '.[llm]'</code>")
    if not krx_available:
        notes.append("KRX 실데이터: <code>pip install '.[data]'</code> (KRX 네트워크 필요)")
    krx_note = (f'<div class="hint">켜려면 — {" · ".join(notes)}</div>' if notes else "")
    if records:
        body = f'<div class="grid">{"".join(_card(r) for r in records)}</div>'
    else:
        body = ('<div class="empty">아직 실행한 백테스트가 없습니다. '
                '위에서 데이터를 골라 <b>백테스트 실행</b>을 눌러보세요.</div>')
    inner = f"""
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
      {nl_option}
      <option value="csv">실데이터 (CSV 업로드)</option>
      {krx_option}
    </select>
  </label>
  <div id="fields-synthetic" class="src-fields">
    <label>전략<select name="strategy">{options}</select></label>
    <label>보유 종목 수<input type="number" name="n_positions" value="20" min="1" max="30"></label>
  </div>
  <div id="fields-nl" class="src-fields" style="display:none">
    <label style="min-width:420px;flex:1">전략 아이디어 (자연어)
      <textarea name="idea" rows="2" placeholder="예: 최근 5일 하락했지만 거래량이 늘어난 종목을 산다"
        style="font:14px inherit;width:100%;background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 11px"></textarea>
    </label>
  </div>
  <div id="fields-csvfile" class="src-fields" style="display:none">
    <label>OHLCV CSV 파일<input type="file" name="csv" accept=".csv"></label>
  </div>
  <div id="fields-krx" class="src-fields" style="display:none">
    <label style="min-width:100%;flex:1">종목 코드 (6자리 · 쉼표/공백/줄바꿈 구분)
      <textarea name="tickers" rows="3" style="font:13px var(--mono);width:100%;background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 11px">{krx_default_tickers}</textarea>
    </label>
    <div class="hint" style="flex-basis:100%">KRX의 전체-종목 스냅샷 조회가 불안정해, KRX 모드는
      <b>여기 적은 종목만</b> 종목별 시세로 받아 백테스트합니다(대형주 기본 채움, 자유 편집). 시장·상위
      시가총액 설정은 KRX에선 무시됩니다. 전략 프리셋·보유 종목 수·리밸런스·기간은 그대로 적용됩니다.</div>
  </div>
  <div id="fields-realdata" class="src-fields" style="display:none">
    <div class="frow">
      {_datefield("start", "시작일", -365)}
      {_datefield("end", "종료일", 0)}
    </div>
    <div class="frow">
      <label>전략 프리셋
        <select id="preset-select">
          <option value="momentum_vol">모멘텀+거래량 (기본)</option>
          <option value="momentum">모멘텀 (6개월 추세)</option>
          <option value="reversal">단기 반전 (5일 반등)</option>
          <option value="lowvol">저변동성 (안정)</option>
          <option value="value_surge">거래대금 급증</option>
        </select>
      </label>
      <label>시장
        <select id="mk-select">
          <option value="KOSPI">코스피</option>
          <option value="KOSDAQ">코스닥</option>
          <option value="KOSPI,KOSDAQ">코스피+코스닥</option>
        </select>
      </label>
      <label>상위 시가총액<input type="number" id="topn-input" value="100" min="10" max="1000" step="10"></label>
      <label>보유 종목 수<input type="number" id="npos-input" value="20" min="1" max="50"></label>
      <label>리밸런스
        <select id="rebal-select">
          <option value="monthly">월간</option>
          <option value="weekly">주간</option>
          <option value="daily">일간</option>
        </select>
      </label>
    </div>
    <div class="presetdesc" id="preset-desc"></div>
    <details class="adv">
      <summary>고급 — DSL 수식 직접 편집 (YAML)</summary>
      <textarea name="config_yaml" rows="4" style="font:12px var(--mono);width:100%;background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 11px">{default_yaml}</textarea>
      <div class="hint">위 폼을 바꾸면 이 YAML이 자동으로 다시 채워집니다. 여기서 직접 고치면 그 값이 그대로 실행됩니다.</div>
    </details>
  </div>
  <button class="go" type="submit">백테스트 실행</button>
</form>
<div class="hint">합성 데이터는 즉시 실행됩니다(네트워크 불필요). CSV는 <b>date, open, high, low, close,
volume, Name</b> long-format 파일을 올리면 실데이터로 동일 파이프라인이 돕니다. KRX는 pykrx로
그 기간의 <b>일봉(EOD)</b>을 받아 같은 파이프라인으로 돌립니다. 실행은 백그라운드 큐에서 처리되고,
실패 포함 자동 기록됩니다.</div>
{krx_note}
{jobs_html}
<h2>최근 실행</h2>
{body}
<script>
(function(){{
  var sel=document.getElementById('source-select');
  var vis={{synthetic:['fields-synthetic'], nl:['fields-nl'],
            csv:['fields-csvfile','fields-realdata'], krx:['fields-krx','fields-realdata']}};
  var all=['fields-synthetic','fields-nl','fields-csvfile','fields-krx','fields-realdata'];
  function upd(){{
    var show=vis[sel.value]||[];
    all.forEach(function(id){{
      var el=document.getElementById(id);
      if (el) el.style.display = (show.indexOf(id)>=0) ? '' : 'none';
    }});
  }}
  sel.addEventListener('change', upd); upd();
}})();
{_CAL_JS}
(function(){{
  var PRESETS={{
    momentum_vol:{{alpha:'rank(returns(close, 120)) * rank(ts_mean(volume, 20) / ts_mean(volume, 60))',
      desc:'6개월 상승 추세와 거래량 증가를 함께 보는 기본 전략'}},
    momentum:{{alpha:'rank(returns(close, 120))',
      desc:'최근 6개월(약 120거래일) 많이 오른 종목을 산다 — 추세추종'}},
    reversal:{{alpha:'rank(-returns(close, 5))',
      desc:'최근 5일 많이 빠진 종목의 단기 반등을 노린다 — 역추세'}},
    lowvol:{{alpha:'rank(-ts_std(returns(close, 1), 20))',
      desc:'최근 20일 변동성이 낮은 안정적인 종목을 산다'}},
    value_surge:{{alpha:'rank(ts_mean(value, 5) / ts_mean(value, 60))',
      desc:'최근 거래대금이 평소보다 급증한(관심 몰린) 종목을 산다'}}
  }};
  function g(id){{return document.getElementById(id);}}
  function buildYaml(){{
    var p=PRESETS[g('preset-select').value]||PRESETS.momentum_vol;
    var mk='['+g('mk-select').value.split(',').join(', ')+']';
    var top=g('topn-input').value||100, npos=g('npos-input').value||20, reb=g('rebal-select').value;
    var y='alpha: "'+p.alpha+'"\\n'
      +'universe: {{market: '+mk+', top_mktcap: '+top+', min_turnover: 1e7}}\\n'
      +'portfolio: {{n_positions: '+npos+', weighting: equal, rebalance: '+reb+'}}';
    var ta=document.querySelector('#fields-realdata textarea[name=config_yaml]');
    if(ta) ta.value=y;
    var dd=g('preset-desc'); if(dd) dd.textContent='➤ '+p.desc;
  }}
  ['preset-select','mk-select','topn-input','npos-input','rebal-select'].forEach(function(id){{
    var el=g(id); if(el){{el.addEventListener('change',buildYaml); el.addEventListener('input',buildYaml);}}
  }});
  if(g('preset-select')) buildYaml();
}})();
</script>"""
    return _shell("대시보드", "dashboard", inner, refresh=2 if active else None)


# --- compare ---------------------------------------------------------------


def compare_page(records: list[RunRecord], pbo: dict | None) -> str:
    ranked = sorted(records, key=lambda r: (r.sharpe if r.sharpe == r.sharpe else -1e9), reverse=True)
    if ranked:
        rows = "".join(
            f'<tr class="{"" if r.survives else "dim"}">'
            f"<td>{_e(r.strategy)}</td><td>{_e(r.source)}</td>"
            f"<td>{_pct(r.cagr)}</td><td>{r.sharpe:.2f}</td><td>{r.max_drawdown:.1%}</td>"
            f"<td>{r.shuffle_p:.3f}</td>"
            f'<td><span class="badge {"pass" if r.survives else "fail"}">'
            f'{"통과" if r.survives else "폐기"}</span></td></tr>'
            for r in ranked
        )
        table = (
            '<table class="tbl"><tr><th>전략</th><th>데이터</th><th>CAGR</th><th>샤프</th>'
            '<th>최대낙폭</th><th>셔플 p</th><th>판정</th></tr>' + rows + "</table>"
        )
    else:
        table = '<div class="empty">비교할 실행이 없습니다. 대시보드에서 먼저 백테스트를 돌려보세요.</div>'

    if pbo:
        pb_badge = ("fail", "과최적화") if pbo["overfit"] else ("pass", "양호")
        pbocard = f"""
<div class="pbocard">
  <div>
    <div class="k">과최적화 확률 (PBO)</div>
    <div class="big">{pbo["pbo"]*100:.0f}%</div>
  </div>
  <div><span class="badge {pb_badge[0]}">{pb_badge[1]}</span></div>
  <div><div class="k">최상위 전략의 디플레이티드 샤프</div><div class="v">{pbo["dsr"]:.2f}</div></div>
  <div><div class="k">후보 전략</div><div class="v">{pbo["n_strategies"]}개 · best={_e(pbo["best"])}</div></div>
  <div style="margin-left:auto;display:flex;gap:12px;align-items:center">
    <a class="report" href="/compare/report" target="_blank">전체 비교 리포트 →</a>
    <form method="post" action="/api/compare"><button class="go" type="submit">다시 분석</button></form>
  </div>
</div>"""
    else:
        pbocard = """
<div class="pbocard">
  <div style="flex:1">
    <div class="k">과최적화 확률 (PBO)</div>
    <div class="v" style="color:var(--muted)">아직 분석하지 않음</div>
  </div>
  <form method="post" action="/api/compare"><button class="go" type="submit">PBO 분석 실행</button></form>
</div>"""

    inner = f"""
<h2>다중검정 PBO 분석 <span style="color:var(--muted);font-weight:500;font-size:11px">(7개 전략 · 합성 데이터)</span></h2>
<div class="desc">여러 전략 중 '표본 내 1등'을 고르는 행위 자체가 요행을 부릅니다. PBO는 그 선택이
표본 밖에서도 통할지를 측정합니다 — 값이 높으면 아래 순위를 믿기 어렵습니다.</div>
{pbocard}
<h2>내 실행 순위 <span style="color:var(--muted);font-weight:500;font-size:11px">(샤프지수 기준 · 폐기는 흐리게)</span></h2>
{table}"""
    return _shell("비교", "compare", inner)


# --- integrity audit -------------------------------------------------------


def audit_page(trials: list[dict], holdout: list[dict]) -> str:
    if trials:
        rows = ""
        for t in trials:
            ok = t.get("status") == "ok"
            m = t.get("metrics") or {}
            label = (t.get("meta") or {}).get("label") or t.get("config_hash", "")[:8]
            sp = m.get("shuffle_p")
            rows += (
                f"<tr><td>{_e(t.get('ts',''))}</td><td>{_e(label)}</td>"
                f'<td><span class="badge {"pass" if ok else "fail"}">{"완료" if ok else "실패"}</span></td>'
                f"<td>{_num(m.get('sharpe'))}</td>"
                f"<td>{_num(sp, '.3f')}</td></tr>"
            )
        trial_tbl = (
            '<table class="tbl"><tr><th>시각 (UTC)</th><th>전략</th><th>상태</th>'
            '<th>샤프</th><th>셔플 p</th></tr>' + rows + "</table>"
        )
    else:
        trial_tbl = '<div class="empty">아직 기록된 시도가 없습니다.</div>'

    if holdout:
        hrows = "".join(
            f"<tr><td>{_e(h.get('ts',''))}</td><td>{_e(h.get('strategy_hash',''))[:12]}</td>"
            f"<td>{_e(h.get('access_index',''))}</td><td>{_e(h.get('reason',''))}</td></tr>"
            for h in holdout
        )
        holdout_html = (
            '<table class="tbl"><tr><th>시각 (UTC)</th><th>전략 해시</th>'
            '<th>접근 횟수</th><th>사유</th></tr>' + hrows + "</table>"
        )
    else:
        holdout_html = ('<div class="banner">홀드아웃은 <b>잠금 상태</b>이며 접근 기록이 없습니다. '
                        '홀드아웃을 여는 모든 접근은 전략별 횟수와 함께 이 감사 로그에 남습니다.</div>')

    inner = f"""
<div class="summary">
  <div><div class="k">기록된 시도 (실패 포함)</div><div class="v">{len(trials)}</div></div>
  <div><div class="k">실패</div><div class="v">{sum(1 for t in trials if t.get('status') != 'ok')}</div></div>
  <div><div class="k">홀드아웃 접근</div><div class="v">{len(holdout)}</div></div>
</div>
<h2>시도 로그 <span style="color:var(--muted);font-weight:500;font-size:11px">(실패 포함 · 최신순)</span></h2>
<div class="desc">모든 실행은 실패까지 자동 기록됩니다 — 다중검정 보정(DSR)의 N이 정확하려면
시도 카운트가 완전해야 하기 때문입니다.</div>
{trial_tbl}
<h2>홀드아웃 접근 감사</h2>
{holdout_html}"""
    return _shell("무결성 감사", "audit", inner)


# --- screener --------------------------------------------------------------

_SCREEN_EXAMPLE = "close > ts_mean(close, 20) and volume > ts_mean(volume, 20) * 2"


_SCREEN_PRESETS = [
    ("mavol", "20일선 위 + 거래량 급등",
     "close > ts_mean(close, 20) and volume > ts_mean(volume, 20) * 2"),
    ("ma20", "20일 이동평균선 위", "close > ts_mean(close, 20)"),
    ("golden", "골든크로스 (5일선 > 20일선)", "ts_mean(close, 5) > ts_mean(close, 20)"),
    ("volsurge", "거래량 급증 (20일 평균 2배)", "volume > ts_mean(volume, 20) * 2"),
    ("near_high", "60일 신고가 근접 (5% 이내)", "close > ts_max(close, 60) * 0.95"),
]


def screen_page(records: list[RunRecord], *, jobs: list | None = None,
                llm_available: bool, krx_available: bool, default_yaml: str) -> str:
    from quantlab.web.service import DEFAULT_KRX_TICKERS  # lazy: avoid import cycle

    jobs = jobs or []
    active = any(getattr(j, "active", False) for j in jobs)
    screens = [r for r in records if r.source == "screen"]
    krx_default_tickers = _e(", ".join(DEFAULT_KRX_TICKERS))
    krx_option = ('<option value="krx">KRX 일봉</option>' if krx_available
                  else '<option value="krx" disabled>KRX (pykrx 미설치)</option>')
    from quantlab.dsl.nl_screen import SUPPORTED_PHRASES  # lazy: avoid import cycle
    nl_examples = _e(" · ".join(SUPPORTED_PHRASES))
    nl_note = ('<div class="hint" style="flex-basis:100%">💡 <b>LLM 키가 있으면</b> 자유로운 문장을 이해합니다.'
               if llm_available else
               '<div class="hint" style="flex-basis:100%">💡 <b>키 없이도</b> 규칙 기반으로 아래 표현을 이해합니다: '
               f'{nl_examples}.')
    nl_field = f"""
    <label style="min-width:340px;flex:1">조건 (자연어 · 한국어)
      <textarea name="criteria" rows="2" placeholder="예: 20일선 위 그리고 거래량 급등"
        style="font:14px inherit;width:100%;background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 11px"></textarea>
    </label>
    {nl_note}</div>"""

    preset_opts = "".join(f'<option value="{_e(expr)}">{_e(label)}</option>'
                          for _, label, expr in _SCREEN_PRESETS)

    if screens:
        rows = "".join(
            f'<tr><td><a href="/screen/{_e(r.id)}">{_e(r.strategy)}</a></td>'
            f"<td>{_e(r.source)}</td><td>{r.n_positions}</td><td>{_e(r.window)}</td>"
            f"<td>{_e(r.created_at)}</td></tr>" for r in screens
        )
        recent = ('<table class="tbl"><tr><th>조건</th><th>데이터</th><th>매칭 종목</th>'
                  '<th>기간</th><th>실행 시각</th></tr>' + rows + "</table>")
    else:
        recent = '<div class="empty">아직 실행한 종목 찾기가 없습니다.</div>'

    inner = f"""
<h2>종목 찾기 (스크리너)</h2>
<div class="desc">조건을 만족하는 종목을 <b>찾아 리스트로</b> 보여주고, 그 종목들을 동일가중으로
담았을 때의 <b>백테스트 성과</b>까지 냅니다. 아래 <b>빠른 조건</b>을 고르면 조건식이 자동으로 채워집니다.</div>
<form class="new" method="post" action="/api/screen" enctype="multipart/form-data">
  <label>데이터
    <select name="source" id="scr-source">
      <option value="csv">CSV 업로드</option>
      {krx_option}
    </select>
  </label>
  <div id="scr-csv" class="src-fields"><label>OHLCV CSV 파일<input type="file" name="csv" accept=".csv"></label></div>
  <div id="scr-krx" class="src-fields" style="display:none">
    <label style="min-width:100%">검색 범위
      <select name="krx_universe" id="scr-krx-univ">
        <option value="basket">대형주 바스켓 (빠름 · 아래 종목 코드만)</option>
        <option value="kospi">코스피 전체 (느림 · 수백 종목)</option>
        <option value="kosdaq">코스닥 전체 (느림)</option>
        <option value="all">코스피+코스닥 전체 (매우 느림)</option>
      </select>
    </label>
    <label id="scr-krx-tickers" style="min-width:100%;flex:1">종목 코드 (6자리 · 쉼표/공백/줄바꿈 구분)
      <textarea name="tickers" rows="2" style="font:13px var(--mono);width:100%;background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 11px">{krx_default_tickers}</textarea>
    </label>
    <div class="hint" style="flex-basis:100%">전체 범위는 종목마다 일봉을 하나씩 받아와 <b>수 분</b>이 걸릴 수 있고,
      KRX 목록 엔드포인트가 불안정하면 실패할 수 있어요. 먼저 <b>바스켓</b>으로 확인 후 넓히길 권합니다.</div>
  </div>
  {_datefield("start", "시작일", -365)}
  {_datefield("end", "종료일", 0)}
  <label>빠른 조건
    <select id="scr-preset">
      <option value="">— 직접 입력 —</option>
      {preset_opts}
    </select>
  </label>
  {nl_field}
  <label style="min-width:340px;flex:1">직접 조건식 (불리언)
    <textarea name="screen_expr" rows="2" placeholder="예: {_SCREEN_EXAMPLE}"
      style="font:12px var(--mono);width:100%;background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 11px"></textarea>
  </label>
  <label style="min-width:300px;flex:1">유니버스·리밸런스 (DSL YAML · alpha는 무시)
    <textarea name="config_yaml" rows="3"
      style="font:12px var(--mono);width:100%;background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 11px">{default_yaml}</textarea>
  </label>
  <button class="go" type="submit">종목 찾기 실행</button>
</form>
<div class="hint">가장 쉬운 방법: <b>조건(자연어)</b> 칸에 한국어로 쓰거나 <b>빠른 조건</b>을 고르세요.
 직접 조건식은 고급용 — 비교 <code>&gt; &lt; &gt;= &lt;=</code> · 결합 <code>and</code> <code>or</code> <code>not</code>
 · 연산자 rank, ts_mean, ts_max, returns, delay … (<code>==</code>는 불가).</div>
{_jobs_section(jobs)}
<h2>최근 종목 찾기</h2>
{recent}
<script>
(function(){{
  var sel=document.getElementById('scr-source');
  var csv=document.getElementById('scr-csv'), krx=document.getElementById('scr-krx');
  function upd(){{
    csv.style.display = (sel.value==='csv') ? '' : 'none';
    krx.style.display = (sel.value==='krx') ? '' : 'none';
  }}
  sel.addEventListener('change', upd); upd();
  var pre=document.getElementById('scr-preset');
  var expr=document.querySelector('textarea[name=screen_expr]');
  if(pre) pre.addEventListener('change', function(){{ if(pre.value) expr.value=pre.value; }});
  var univ=document.getElementById('scr-krx-univ');
  var tick=document.getElementById('scr-krx-tickers');
  function updUniv(){{ if(tick) tick.style.display = (univ.value==='basket') ? '' : 'none'; }}
  if(univ){{ univ.addEventListener('change', updUniv); updUniv(); }}
}})();
{_CAL_JS}
</script>"""
    return _shell("종목 찾기", "screen", inner, refresh=2 if active else None)


def screen_result_page(r: RunRecord, snap: dict) -> str:
    matches = snap.get("matches", [])
    if matches:
        rows = "".join(
            f'<tr><td>{_e(m.get("name") or m["ticker"])}</td><td>{_e(m["ticker"])}</td>'
            f'<td>{m.get("close", float("nan")):,.0f}</td></tr>' for m in matches
        )
        table = ('<table class="tbl"><tr><th>종목</th><th>코드</th><th>종가</th></tr>'
                 + rows + "</table>")
    else:
        table = '<div class="empty">조건을 만족하는 종목이 없습니다.</div>'
    crit = snap.get("criteria") or ""
    inner = f"""
<h2 style="margin-top:20px">종목 찾기 결과</h2>
{f'<div class="desc">{_e(crit)}</div>' if crit else ""}
<div class="dsl"><span>조건식</span><code>{_e(snap.get("expr",""))}</code></div>
<div class="detailmeta">
  <div><div class="k">기준일</div><div class="v">{_e(snap.get("ref_date",""))}</div></div>
  <div><div class="k">매칭 종목</div><div class="v">{len(matches)}</div></div>
  <div><div class="k">유니버스</div><div class="v">{snap.get("universe_size",0)}</div></div>
  <div><div class="k">기간</div><div class="v">{_e(r.window)}</div></div>
</div>
<div class="actions">
  <a class="report" href="/runs/{_e(r.id)}/report" target="_blank">이 종목들 담았을 때 성과 리포트 ↗</a>
  <a class="report" href="/screen/{_e(r.id)}/matches.csv">종목 리스트 CSV 내려받기 ↓</a>
  <form method="post" action="/runs/{_e(r.id)}/delete" class="inline" style="margin-left:auto"
        onsubmit="return confirm('삭제할까요?')"><button class="danger" type="submit">삭제</button></form>
</div>
<h2>기준일({_e(snap.get("ref_date",""))}) 매칭 종목 · {len(matches)}개</h2>
{table}"""
    return _shell("종목 찾기 결과", "screen", inner)


# --- run detail ------------------------------------------------------------


def _repro_section(r: RunRecord, bundle: dict | None) -> str:
    if bundle is None:
        return ""
    ver = bundle.get("version", {})
    verline = " · ".join(
        f"{k} {_e(str(v))}" for k, v in ver.items()) if ver else ""
    reproducible = bool(bundle.get("reproducible"))
    if reproducible:
        rbadge = '<span class="badge pass">자동 재현</span>'
    else:
        rbadge = '<span class="badge">외부 데이터</span>'
    reason = bundle.get("reason") or ""
    v = bundle.get("verification")
    if v is None:
        vline = '<span class="hint">아직 검증하지 않음</span>'
    elif v.get("matches"):
        vline = ('<span class="badge pass">지문 일치</span> '
                 f'<code>{_e(str(v.get("reproduced_fingerprint","")))}</code>'
                 f' · {_e(str(v.get("checked_at","")))}')
    else:
        vline = ('<span class="badge fail">지문 불일치</span> '
                 f'<code>{_e(str(v.get("reproduced_fingerprint","")))}</code>'
                 f' · {_e(str(v.get("checked_at","")))}')
    if reproducible:
        verify = (f'<form method="post" action="/runs/{_e(r.id)}/reproduce" class="inline">'
                  f'<button class="go" type="submit">재현 검증</button></form>')
    else:
        verify = f'<span class="hint">{_e(reason)}</span>' if reason else ""
    inp = bundle.get("inputs", {}) or {}
    pin = ""
    if inp.get("data_sha256"):
        pin = (f'<div class="desc">데이터 핀: <code>{_e(str(inp.get("data_name","")))}</code> '
               f'· sha256 <code>{_e(str(inp["data_sha256"])[:16])}</code> '
               f'(이 파일 그대로 오프라인 재현)</div>')
    return f"""
<h2>재현성 번들</h2>
<div class="desc">실행에 필요한 입력·시드·버전과 결과 <b>지문</b>을 함께 저장합니다. {rbadge}</div>
<div class="detailmeta">
  <div><div class="k">결과 지문</div><div class="v"><code>{_e(str(bundle.get("fingerprint","")))}</code></div></div>
  <div><div class="k">종류</div><div class="v">{_e(str(bundle.get("kind","")))}</div></div>
  <div><div class="k">생성 시각</div><div class="v">{_e(str(bundle.get("created_at","")))}</div></div>
</div>
{pin}
{f'<div class="desc">{verline}</div>' if verline else ""}
<div class="desc">검증: {vline}</div>
<div class="actions">
  {verify}
  <a class="report" href="/runs/{_e(r.id)}/bundle.json" style="margin-left:auto">번들 JSON 다운로드 ↓</a>
</div>"""


def run_detail_page(r: RunRecord, bundle: dict | None = None) -> str:
    badge = ("pass", "통과") if r.survives else ("fail", "폐기")
    dd_neg = " neg" if r.max_drawdown < 0 else ""
    scope = f"유니버스 {r.universe_size} · {_e(r.window)}" if r.universe_size else f"종목 {r.n_positions}개"
    if r.source == "synthetic":
        rerun = (f'<form method="post" action="/runs/{_e(r.id)}/rerun" class="inline">'
                 f'<button class="go" type="submit">재실행</button></form>')
    else:
        rerun = '<span class="hint">CSV 재실행은 파일 재업로드가 필요합니다</span>'
    inner = f"""
<h2 style="margin-top:20px">{_e(r.strategy)}
  <span class="badge {badge[0]}" style="margin-left:8px">{badge[1]}</span></h2>
<div class="desc">{_e(r.source)} · {scope} · {_e(r.created_at)}</div>
{f'<div class="dsl"><span>생성된 팩터식</span><code>{_e(r.note)}</code></div>' if r.note else ""}
<div class="detailmeta">
  <div><div class="k">연복리수익 (CAGR)</div><div class="v">{_pct(r.cagr)}</div></div>
  <div><div class="k">샤프지수</div><div class="v">{r.sharpe:.2f}</div></div>
  <div><div class="k">최대낙폭</div><div class="v{dd_neg}">{r.max_drawdown:.1%}</div></div>
  <div><div class="k">셔플 p</div><div class="v">{r.shuffle_p:.3f}</div></div>
  <div><div class="k">기록된 시도</div><div class="v">{r.trials_logged}</div></div>
</div>
<div class="actions">
  {rerun}
  <form method="post" action="/runs/{_e(r.id)}/delete" class="inline"
        onsubmit="return confirm('이 실행을 삭제할까요? 리포트도 함께 삭제됩니다.')">
    <button class="danger" type="submit">삭제</button>
  </form>
  <a class="report" href="/runs/{_e(r.id)}/report" target="_blank" style="margin-left:auto">새 탭에서 리포트 열기 ↗</a>
</div>
{_repro_section(r, bundle)}
<h2>리포트</h2>
<iframe class="report" src="/runs/{_e(r.id)}/report" title="report"></iframe>"""
    return _shell(r.strategy, "dashboard", inner)
