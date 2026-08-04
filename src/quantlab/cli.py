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
