"""``quantlab`` CLI entry point (F6).

M0 ships a ``data`` command group for building/inspecting the point-in-time
universe and warming the price cache. Backtest/report commands arrive in M1.
"""

from __future__ import annotations

import typer

from quantlab.config import get_settings
from quantlab.types import Market, UniverseSpec, as_date

app = typer.Typer(help="AI Quant Lab — KRX quant research (backtest-only MVP).", no_args_is_help=True)
data_app = typer.Typer(help="Data layer: universe, cache.", no_args_is_help=True)
app.add_typer(data_app, name="data")


@app.command()
def demo(
    strategy: str = typer.Option("momentum_volume_combo", help="Hand-crafted strategy name."),
    n_positions: int = typer.Option(10, help="Names held long."),
    shuffles: int = typer.Option(50, help="Shuffle-control iterations (F7.4)."),
) -> None:
    """Run the full M1 pipeline on synthetic data (no live KRX needed).

    strategy -> weights -> backtest -> metrics -> shuffle control -> trial log.
    """
    from quantlab.demo import run_demo
    from quantlab.strategies import STRATEGIES

    settings = get_settings()
    settings.ensure_dirs()
    if strategy not in STRATEGIES:
        raise typer.BadParameter(f"choose from {list(STRATEGIES)}")

    out = run_demo(strategy, n_positions, settings.experiments_dir / "trials.jsonl", shuffles)
    _print_eval(out)


def _print_eval(out: dict) -> None:
    s, shuf = out["stats"], out["shuffle"]
    typer.echo(f"strategy      : {out['strategy']}  (config {out['config_hash']})")
    typer.echo(f"total return  : {s['total_return']:+.1%}   CAGR {s['cagr']:+.1%}")
    typer.echo(f"Sharpe        : {s['sharpe']:.2f}   Sortino {s['sortino']:.2f}")
    typer.echo(f"max drawdown  : {s['max_drawdown']:.1%}   avg turnover {s['avg_turnover']:.2f}")
    typer.echo(f"cost drag     : {s['cost_drag']:.2%}")
    typer.echo(f"IC mean/IR    : {out['ic_mean']:+.3f} / {out['ic_ir']:+.2f}")
    verdict = "SURVIVES (p<0.05)" if shuf.survives else "DISCARD (p>=0.05)"
    typer.echo(f"shuffle test  : p={shuf.p_value:.3f}  [{verdict}]  vs null "
               f"{shuf.null_mean:+.3f}±{shuf.null_std:.3f}")
    typer.echo(f"trials logged : {out['trials_logged']}  (F7.1, incl. failures)")


@app.command()
def strategy(
    config_file: str = typer.Argument(..., help="Path to a strategy YAML (alpha/universe/portfolio)."),
    shuffles: int = typer.Option(50, help="Shuffle-control iterations (F7.4)."),
) -> None:
    """Backtest a DSL strategy config on synthetic data (M2 -> M1 pipeline)."""
    from pathlib import Path

    from quantlab.demo import run_config
    from quantlab.dsl.config import StrategyConfig

    settings = get_settings()
    settings.ensure_dirs()
    cfg = StrategyConfig.from_yaml(Path(config_file).read_text(encoding="utf-8"))
    out = run_config(cfg, settings.experiments_dir / "trials.jsonl", shuffles)
    _print_eval(out)


@app.command()
def backtest(
    config_file: str = typer.Argument(..., help="Strategy YAML to backtest on real KRX data."),
    date_from: str = typer.Option(..., "--from", help="Backtest start (YYYY-MM-DD / YYYYMMDD)."),
    date_to: str = typer.Option(..., "--to", help="Backtest end (YYYY-MM-DD / YYYYMMDD)."),
    shuffles: int = typer.Option(50, help="Shuffle-control iterations (F7.4)."),
) -> None:
    """Run a strategy on real KRX data end-to-end (needs the [data] extra + KRX access).

    Reconstructs the point-in-time universe, assembles adjusted panels, backtests,
    and writes an HTML report — the same pipeline the demos use, fed by pykrx.
    """
    from pathlib import Path

    from quantlab.dsl.config import StrategyConfig
    from quantlab.data.pykrx_source import PykrxDataSource
    from quantlab.run import run_backtest
    from quantlab.types import as_date

    settings = get_settings()
    settings.ensure_dirs()
    cfg = StrategyConfig.from_yaml(Path(config_file).read_text(encoding="utf-8"))
    out_dir = settings.experiments_dir / cfg.content_hash()
    out = run_backtest(
        PykrxDataSource(), cfg,
        start=as_date(date_from), end=as_date(date_to),
        cache_dir=settings.cache_dir, out_dir=out_dir, n_shuffles=shuffles,
    )
    typer.echo(f"universe      : {out['universe_size']} names")
    _print_eval(out)
    typer.echo(f"report        : {out['report']}")


@app.command()
def report(
    config_file: str = typer.Argument(..., help="Strategy YAML to backtest and report."),
    shuffles: int = typer.Option(50, help="Shuffle-control iterations."),
) -> None:
    """Backtest a DSL strategy and write a self-contained HTML report (M4)."""
    from pathlib import Path

    from quantlab.demo import run_config, synthetic_market, write_strategy_report
    from quantlab.dsl.config import StrategyConfig

    settings = get_settings()
    settings.ensure_dirs()
    cfg = StrategyConfig.from_yaml(Path(config_file).read_text(encoding="utf-8"))
    out = run_config(cfg, settings.experiments_dir / "trials.jsonl", shuffles)
    exp_dir = settings.experiments_dir / out["config_hash"]
    close, _ = synthetic_market()  # same deterministic panel run_config used
    path = write_strategy_report(out, close, exp_dir)
    _print_eval(out)
    typer.echo(f"report        : {path}")


@app.command()
def compare() -> None:
    """Compare all hand-crafted strategies with PBO + Deflated Sharpe (M4)."""
    from quantlab.demo import run_comparison

    settings = get_settings()
    settings.ensure_dirs()
    out = run_comparison(settings.experiments_dir)
    pbo = out["pbo"]
    verdict = "OVERFIT" if pbo.overfit else "OK"
    typer.echo(f"strategies    : {out['n']}   in-sample best: {out['best']}")
    typer.echo(f"PBO           : {pbo.pbo:.2f}  [{verdict}]  ({pbo.n_combinations} splits)")
    typer.echo(f"Deflated Sharpe of best (P[SR>0]): {out['dsr']:.2f}")
    typer.echo(f"report        : {out['report']}")


@app.command("ml-demo")
def ml_demo(
    shuffles: int = typer.Option(50, help="Shuffle-control iterations (F7.4)."),
) -> None:
    """Train an ML rank model walk-forward on synthetic (signal-injected) data (M3).

    Reports out-of-sample Rank IC, then runs the predictions through the M1
    backtest + integrity pipeline. With a real injected signal it should
    SURVIVE the shuffle control.
    """
    from quantlab.demo import run_ml_demo

    settings = get_settings()
    settings.ensure_dirs()
    out = run_ml_demo(settings.experiments_dir / "trials.jsonl", shuffles)
    ml = out["ml"]
    typer.echo(f"[walk-forward OOS]  Rank IC {ml['rank_ic_mean']:+.3f}  "
               f"IC-IR {ml['ic_ir']:+.2f}  q-spread {ml['quantile_spread']:+.4f}  "
               f"({ml['n_days']}d)")
    _print_eval(out)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address."),
    port: int = typer.Option(8000, help="Port."),
    reload: bool = typer.Option(False, help="Auto-reload on code changes (dev)."),
) -> None:
    """Launch the web dashboard (M5). Needs the `web` extra: pip install -e '.[web]'."""
    try:
        import uvicorn  # noqa: F401
    except ModuleNotFoundError as exc:  # pragma: no cover - import guard
        raise SystemExit(
            "web extra not installed — run: pip install -e '.[web]'"
        ) from exc
    typer.echo(f"dashboard → http://{host}:{port}")
    uvicorn.run("quantlab.web.app:create_app", host=host, port=port, reload=reload, factory=True)


@app.command()
def info() -> None:
    """Show effective settings (paths, cost model)."""
    s = get_settings()
    typer.echo(f"cache_dir       : {s.cache_dir}")
    typer.echo(f"experiments_dir : {s.experiments_dir}")
    typer.echo(f"price_limit     : ±{s.price_limit_pct:.0%}")
    typer.echo(f"round-trip cost : {s.cost.round_trip_bps:.1f} bps")


@data_app.command("universe")
def build_universe(
    on: str = typer.Argument(..., help="Rebalance date (YYYY-MM-DD or YYYYMMDD)."),
    top: int = typer.Option(300, help="Top-N by market cap."),
    min_turnover: float = typer.Option(5e8, help="20-day median trading-value floor (KRW)."),
    kospi_only: bool = typer.Option(False, help="Restrict to KOSPI."),
    no_liquidity: bool = typer.Option(
        False, help="Skip the liquidity filter (no price fetches)."
    ),
) -> None:
    """Reconstruct and print the point-in-time universe for a date (§11).

    Requires the ``[data]`` extra (pykrx) for live reconstruction.
    """
    from quantlab.data.cache import OHLCVCache, PriceStore
    from quantlab.data.pykrx_source import PykrxDataSource
    from quantlab.data.universe import UniverseBuilder

    settings = get_settings()
    settings.ensure_dirs()

    markets = (Market.KOSPI,) if kospi_only else (Market.KOSPI, Market.KOSDAQ)
    spec = UniverseSpec(markets=markets, top_mktcap=top, min_turnover=min_turnover)

    source = PykrxDataSource()
    price_store = None if no_liquidity else PriceStore(source, OHLCVCache(settings.cache_dir))
    builder = UniverseBuilder(source, price_store=price_store)

    tickers = builder.build(as_date(on), spec)
    typer.echo(f"# {spec.describe()} @ {on} -> {len(tickers)} names")
    for t in tickers:
        typer.echo(t)


if __name__ == "__main__":
    app()
