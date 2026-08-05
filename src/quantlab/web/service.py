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
from quantlab.web.repro import pin_file, write_bundle
from quantlab.web.store import RunRecord, RunStore, _now_iso


def available_strategies() -> list[str]:
    return list(STRATEGIES)


def get_llm_client():
    """Return a real LLM client if one is configured, else None.

    Requires the `llm` extra (``anthropic``) *and* an ``ANTHROPIC_API_KEY``. Absent
    either, the dashboard runs fine — natural-language input and commentary are
    simply disabled, not broken.
    """
    import os

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return None
    from quantlab.dsl.llm import AnthropicClient
    return AnthropicClient()


def _safe_name(source, ticker: str) -> str:
    try:
        return source.get_ticker_name(ticker) or ticker
    except Exception:  # noqa: BLE001 — metadata is best-effort
        return ticker


def read_screen(store: RunStore, run_id: str) -> dict | None:
    """The persisted snapshot (matching stocks) for a screen run."""
    import json

    p = store.base / "runs" / run_id / "screen.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def run_screen(
    store: RunStore,
    *,
    source,
    config_yaml: str,
    start: date,
    end: date,
    criteria: str | None = None,
    screen_expr: str | None = None,
    client=None,
    n_shuffles: int = 50,
    warmup_days: int = 400,
    ref_date=None,
    data_label: str = "실데이터",
) -> RunRecord:
    """Screen a universe by a boolean condition, then backtest the matches.

    Natural-language ``criteria`` is turned into a validated boolean filter (or pass
    ``screen_expr`` directly). At the reference date (default: last day) the matching
    stocks are listed; over the window they are held equal-weight (rebalanced per the
    config) and run through the standard backtest + integrity pipeline.
    """
    import json
    from datetime import timedelta

    import pandas as pd

    from quantlab.data.cache import OHLCVCache, PriceStore
    from quantlab.data.panels import adjusted_panels
    from quantlab.data.universe import UniverseBuilder
    from quantlab.dsl.config import StrategyConfig
    from quantlab.dsl.screen import compile_screen
    from quantlab.factors.portfolio import apply_rebalance

    config = StrategyConfig.from_yaml(config_yaml)
    if screen_expr is None:
        if client is None:
            raise ValueError("LLM is not configured (set ANTHROPIC_API_KEY and install '.[llm]')")
        if not (criteria or "").strip():
            raise ValueError("조건을 입력하세요")
        from quantlab.dsl.llm import ScreenGenerator
        screen_expr = ScreenGenerator(client).generate(criteria)
    screen_fn = compile_screen(screen_expr)

    created = _now_iso()
    run_id = RunRecord.new_id(created, "screen")
    run_dir = store.run_dir(run_id)

    px = PriceStore(source, OHLCVCache(store.base / "cache" / run_id))
    tickers = UniverseBuilder(source, price_store=px).build(start, config.universe.to_spec())
    if not tickers:
        raise ValueError("빈 유니버스 — 날짜/시장/필터를 확인하세요")
    panels = adjusted_panels(px, tickers, start - timedelta(days=warmup_days), end)
    close = panels["close"]
    ctx = {"open": panels["open"], "high": panels["high"], "low": panels["low"],
           "close": close, "volume": panels["volume"], "value": close * panels["volume"]}

    in_window = close.index >= pd.Timestamp(start)
    mask = screen_fn(ctx).loc[in_window].reindex(columns=close.columns).fillna(False)
    close_w = close.loc[in_window]

    # snapshot at the reference date (default: last day in the window)
    ref_ts = pd.Timestamp(ref_date) if ref_date else mask.index[-1]
    if ref_ts not in mask.index:
        earlier = mask.index[mask.index <= ref_ts]
        ref_ts = earlier[-1] if len(earlier) else mask.index[-1]
    passing = [t for t in mask.columns if bool(mask.loc[ref_ts, t])]
    matches = [{"ticker": t, "name": _safe_name(source, t),
                "close": float(close_w.loc[ref_ts, t])} for t in passing]

    # backtest: hold the matches equal-weight, rebalanced per the config
    w = mask.astype(float)
    denom = w.sum(axis=1)
    weights = w.div(denom.where(denom > 0), axis=0).fillna(0.0)   # equal-weight the matches
    weights = apply_rebalance(weights, config.portfolio.rebalance)
    out = _evaluate(mask.astype(float), weights, close_w, store.base / "trials.jsonl",
                    n_shuffles, label="screen")
    write_strategy_report(
        out, close_w, run_dir, client=client,
        subtitle=f"종목 찾기 · {data_label} · {start:%Y-%m-%d}→{end:%Y-%m-%d} · "
                 f"{ref_ts:%Y-%m-%d} 기준 {len(matches)}종목",
    )

    (run_dir / "screen.json").write_text(json.dumps({
        "expr": screen_expr, "criteria": criteria or "", "ref_date": f"{ref_ts:%Y-%m-%d}",
        "universe_size": len(tickers), "data_label": data_label, "matches": matches,
    }, ensure_ascii=False), encoding="utf-8")
    write_bundle(run_dir, kind="screen", reproducible=False, out=out,
                 reason="외부 데이터 의존 — 조건식은 저장됨, 데이터 고정 시 수동 재현 가능.",
                 inputs={"expr": screen_expr, "window": f"{start:%Y-%m-%d}→{end:%Y-%m-%d}",
                         "n_shuffles": n_shuffles})

    record = _record_from_out(
        out, id=run_id, created_at=created,
        strategy=(criteria or screen_expr)[:48].replace("\n", " "), source="screen",
        n_positions=len(matches), universe_size=len(tickers),
        window=f"{start:%Y-%m-%d}→{end:%Y-%m-%d}", note=screen_expr,
    )
    store.append(record)
    return record


def krx_available() -> bool:
    """True when the live KRX source can run (the `data` extra is installed)."""
    try:
        import pykrx  # noqa: F401
        return True
    except ImportError:
        return False


# A default basket of liquid large-caps (KOSPI + a few KOSDAQ), used when KRX's
# cross-sectional snapshot endpoints are down so we can't rank a universe by
# market cap. These are public ticker *codes* only — prices come live from the
# working per-ticker OHLCV endpoint. Editable by the user in the UI.
DEFAULT_KRX_TICKERS = [
    "005930", "000660", "373220", "207940", "005380", "000270", "068270",
    "005490", "035420", "035720", "051910", "006400", "028260", "105560",
    "055550", "012330", "003670", "066570", "015760", "032830", "017670",
    "034730", "096770", "018260", "011200", "010130", "009150", "086790",
    "033780", "090430", "247540", "086520", "196170",
]


def parse_tickers(raw: str | None) -> list[str]:
    """Parse a free-form ticker list (comma / whitespace / newline separated) into
    6-digit KRX codes. Non-conforming tokens are dropped; order/uniqueness kept."""
    import re

    if not raw:
        return []
    out, seen = [], set()
    for tok in re.split(r"[\s,]+", raw.strip()):
        tok = tok.strip().zfill(6) if tok.strip().isdigit() else tok.strip()
        if re.fullmatch(r"\d{6}", tok) and tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def run_krx_backtest(
    store: RunStore,
    *,
    config_yaml: str,
    start: date,
    end: date,
    n_shuffles: int = 50,
    client=None,
    source=None,
    tickers: list[str] | None = None,
) -> RunRecord:
    """Backtest a DSL strategy on live KRX daily data (pykrx), same path as CSV.

    KRX's cross-sectional snapshot endpoints (market-cap / whole-market OHLCV)
    are frequently unavailable while per-ticker OHLCV keeps working, so the KRX
    universe is an **explicit basket** (``tickers``; defaults to
    :data:`DEFAULT_KRX_TICKERS`) fetched one code at a time — no snapshot calls.

    ``source`` is injectable so tests drive a fake :class:`DataSource`; in
    production it defaults to :class:`PykrxDataSource` (needs the `data` extra +
    KRX network access — an ImportError/network failure surfaces as a failed job).
    """
    from quantlab.dsl.config import StrategyConfig
    from quantlab.run import run_backtest

    if source is None:
        from quantlab.data.pykrx_source import PykrxDataSource
        source = PykrxDataSource()
    config = StrategyConfig.from_yaml(config_yaml)
    # Explicit basket → per-ticker fetch only (no snapshot endpoints). None →
    # auto-universe via UniverseBuilder (needs the snapshot endpoints to be up).
    basket = list(tickers) if tickers else None

    created = _now_iso()
    label = config.content_hash()
    run_id = RunRecord.new_id(created, f"krx-{label[:8]}")
    run_dir = store.run_dir(run_id)
    out = run_backtest(
        source, config, start=start, end=end,
        cache_dir=store.base / "cache" / run_id, out_dir=run_dir,
        n_shuffles=n_shuffles, data_label="KRX 실데이터 (일봉)",
        trials_path=store.base / "trials.jsonl", client=client,
        tickers=basket,
    )
    write_bundle(run_dir, kind="krx", reproducible=False, out=out,
                 reason="KRX 벤더 데이터 핀 필요 (조정/정정으로 값이 바뀔 수 있음).",
                 inputs={"config_hash": label, "window": f"{start:%Y-%m-%d}→{end:%Y-%m-%d}",
                         "tickers": basket, "n_shuffles": n_shuffles})
    record = _record_from_out(
        out, id=run_id, created_at=created, strategy=f"krx:{label[:8]}", source="krx",
        n_positions=int(getattr(config.portfolio, "n_positions", 0)),
        universe_size=int(out.get("universe_size", 0)),
        window=f"{start:%Y-%m-%d}→{end:%Y-%m-%d}",
        note=(f"KRX 바스켓 {len(basket)}종목" if basket else ""),
    )
    store.append(record)
    return record


def run_synthetic_backtest(
    store: RunStore,
    *,
    strategy: str,
    n_positions: int = 20,
    n_shuffles: int = 50,
    trials_path: str | Path | None = None,
    client=None,
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
        client=client,
    )
    write_bundle(run_dir, kind="synthetic", reproducible=True, out=out,
                 inputs={"strategy": strategy, "n_positions": n_positions,
                         "n_shuffles": n_shuffles})

    record = _record_from_out(
        out, id=run_id, created_at=created, strategy=strategy, source="synthetic",
        n_positions=n_positions,
    )
    store.append(record)
    return record


def run_nl_backtest(
    store: RunStore,
    *,
    idea: str,
    client,
    n_shuffles: int = 50,
    trials_path: str | Path | None = None,
) -> RunRecord:
    """Natural-language idea → LLM-generated DSL config → synthetic backtest.

    The LLM only proposes the config; the whitelist parser validates it, so an
    unsafe/invalid expression is rejected, not trusted. The report embeds an LLM
    interpretation of the result.
    """
    from quantlab.dsl.llm import StrategyGenerator
    from quantlab.dsl.parser import compile_alpha
    from quantlab.dsl.runner import strategy_weights

    if client is None:
        raise ValueError("LLM is not configured (set ANTHROPIC_API_KEY and install '.[llm]')")
    if not idea.strip():
        raise ValueError("아이디어를 입력하세요")

    config = StrategyGenerator(client).generate(idea)   # validated StrategyConfig
    trials_path = Path(trials_path) if trials_path else store.base / "trials.jsonl"

    close, volume = synthetic_market()
    context = {"open": close, "high": close, "low": close, "close": close,
               "volume": volume, "value": close * volume}
    alpha = compile_alpha(config.alpha)(context)
    weights = strategy_weights(config, context)
    out = _evaluate(alpha, weights, close, trials_path, n_shuffles, label=config.content_hash())

    created = _now_iso()
    run_id = RunRecord.new_id(created, "nl-" + config.content_hash()[:8])
    run_dir = store.run_dir(run_id)
    label = idea.strip().replace("\n", " ")[:48]
    write_strategy_report(
        out, close, run_dir, subtitle=f"자연어: {label} · 합성 데이터", client=client,
    )
    write_bundle(run_dir, kind="nl", reproducible=False, out=out,
                 reason="LLM 생성 — 조건식은 저장됨. 합성 데이터라 조건 고정 시 수동 재현 가능.",
                 inputs={"idea": idea, "alpha": config.alpha, "n_shuffles": n_shuffles})
    record = _record_from_out(
        out, id=run_id, created_at=created, strategy=label, source="nl",
        n_positions=int(getattr(config.portfolio, "n_positions", 0)),
        note=config.alpha,
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
    client=None,
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
        client=client,
    )
    pin = pin_file(run_dir, csv_path)   # copy + hash the source CSV → offline re-run
    write_bundle(run_dir, kind="csv", reproducible=True, out=out,
                 inputs={"config_hash": label, "config_yaml": config_yaml,
                         "data_name": pin["name"], "data_sha256": pin["sha256"],
                         "data_bytes": pin["bytes"], "ticker_col": ticker_col,
                         "data_label": data_label,
                         "start": f"{start:%Y-%m-%d}", "end": f"{end:%Y-%m-%d}",
                         "window": f"{start:%Y-%m-%d}→{end:%Y-%m-%d}",
                         "n_shuffles": n_shuffles})
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
                     n_positions: int, universe_size: int = 0, window: str = "",
                     note: str = "") -> RunRecord:
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
        universe_size=universe_size, window=window, note=note,
    )
