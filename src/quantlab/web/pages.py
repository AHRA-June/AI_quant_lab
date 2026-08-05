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
"""

DEFAULT_CONFIG_YAML = """alpha: "rank(returns(close, 120)) * rank(ts_mean(volume, 20) / ts_mean(volume, 60))"
universe: {market: [KOSPI], top_mktcap: 100, min_turnover: 1e7}
portfolio: {n_positions: 20, weighting: equal, rebalance: monthly}"""


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
    items = [("/", "대시보드", "dashboard"), ("/compare", "비교", "compare"),
             ("/audit", "무결성 감사", "audit")]
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
                   llm_available: bool = False) -> str:
    jobs = jobs or []
    survived = sum(1 for r in records if r.survives)
    options = "".join(f'<option value="{_e(s)}">{_e(s)}</option>' for s in strategies)
    default_yaml = _e(DEFAULT_CONFIG_YAML)
    jobs_html = _jobs_section(jobs)
    active = any(getattr(j, "active", False) for j in jobs)
    nl_option = ('<option value="nl">자연어 아이디어 (LLM)</option>' if llm_available
                 else '<option value="nl" disabled>자연어 아이디어 (LLM 미설정)</option>')
    nl_note = ("" if llm_available else
               '<div class="hint">자연어 입력을 켜려면 <b>ANTHROPIC_API_KEY</b>를 설정하고 '
               "<code>pip install '.[llm]'</code> 하세요.</div>")
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
  <div id="fields-csv" class="src-fields" style="display:none">
    <label>OHLCV CSV 파일<input type="file" name="csv" accept=".csv"></label>
    <label>시작일<input type="date" name="start"></label>
    <label>종료일<input type="date" name="end"></label>
    <label style="min-width:320px;flex:1">전략 설정 (DSL YAML)
      <textarea name="config_yaml" rows="4" style="font:12px var(--mono);width:100%;background:var(--panel2);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:9px 11px">{default_yaml}</textarea>
    </label>
  </div>
  <button class="go" type="submit">백테스트 실행</button>
</form>
<div class="hint">합성 데이터는 즉시 실행됩니다(네트워크 불필요). CSV는 <b>date, open, high, low, close,
volume, Name</b> 컬럼의 long-format 파일을 올리면 실데이터로 동일 파이프라인이 돕니다. 실행은
백그라운드 작업 큐에서 처리되고(오래 걸려도 화면이 멈추지 않음), 실패 포함 자동 기록됩니다.</div>
{nl_note}
{jobs_html}
<h2>최근 실행</h2>
{body}
<script>
(function(){{
  var sel=document.getElementById('source-select');
  var map={{synthetic:'fields-synthetic', nl:'fields-nl', csv:'fields-csv'}};
  function upd(){{
    for (var k in map){{
      var el=document.getElementById(map[k]);
      if (el) el.style.display = (sel.value===k) ? '' : 'none';
    }}
  }}
  sel.addEventListener('change', upd); upd();
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


# --- run detail ------------------------------------------------------------


def run_detail_page(r: RunRecord) -> str:
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
<h2>리포트</h2>
<iframe class="report" src="/runs/{_e(r.id)}/report" title="report"></iframe>"""
    return _shell(r.strategy, "dashboard", inner)
