"""End-to-end backtest on **real** market data via :class:`CsvDataSource`.

Fetches a public long-format OHLCV CSV (S&P 500 constituents, daily, 2013–2018)
once into the gitignored ``data_cache/``, then runs the *same* pipeline the live
KRX source uses — point-in-time universe → adjusted panels → DSL alpha →
target-weight engine → research-integrity checks → self-contained HTML report.

Why this exists: the live pykrx source needs KRX network access, which is often
unavailable (locked-down CI, egress policy). This proves the whole stack on real
prices through a file-backed source, with no vendor lock-in.

    python examples/run_sp500.py

Data: https://raw.githubusercontent.com/plotly/datasets — "all_stocks_5yr.csv",
a mirror of the well-known Kaggle S&P 500 daily dataset. Prices are the vendor's
consolidated close (no separate split factor), and the universe ranks by a
trailing dollar-volume proxy — see CsvDataSource's module docstring. Costs are
the repo's KRX-calibrated defaults; treat the absolute return as illustrative,
the *pipeline* as the point.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from urllib.request import urlopen

from quantlab.config import get_settings
from quantlab.data.csv_source import CsvDataSource
from quantlab.dsl.config import StrategyConfig
from quantlab.run import run_backtest

DATA_URL = "https://raw.githubusercontent.com/plotly/datasets/master/all_stocks_5yr.csv"

# Six-month momentum, tilted by a rising-volume signal — the hand-crafted
# momentum_volume_combo shape, expressed in the whitelisted DSL.
CONFIG = StrategyConfig.from_yaml(
    """
alpha: "rank(returns(close, 120)) * rank(ts_mean(volume, 20) / ts_mean(volume, 60))"
universe: {market: [KOSPI], top_mktcap: 100, min_turnover: 1e7, turnover_lookback: 20}
portfolio: {n_positions: 20, weighting: equal, rebalance: monthly}
"""
)

# A clean window fully inside the dataset's 2013-02-08 → 2018-02-07 span (leaves
# room ahead of START for the 120-day momentum warm-up).
START, END = date(2014, 1, 2), date(2018, 2, 1)


def _download(dest: Path) -> None:
    if dest.exists():
        print(f"data      : cached {dest} ({dest.stat().st_size / 1e6:.1f} MB)")
        return
    print(f"data      : downloading {DATA_URL}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(DATA_URL, timeout=120) as resp:  # honors HTTPS_PROXY + CA bundle
        dest.write_bytes(resp.read())
    print(f"          : saved {dest} ({dest.stat().st_size / 1e6:.1f} MB)")


def main() -> int:
    settings = get_settings()
    settings.ensure_dirs()

    csv_path = settings.cache_dir / "sp500_all_stocks_5yr.csv"
    try:
        _download(csv_path)
    except Exception as exc:  # noqa: BLE001 — surface the real network reason
        print(f"\ndownload failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print(
            "The data host may be blocked by this session's egress policy. "
            "Provide the CSV at the path above and re-run.",
            file=sys.stderr,
        )
        return 2

    source = CsvDataSource.from_csv(csv_path)  # ticker column defaults to 'Name'
    print(f"loaded    : {len(source.tickers)} tickers")

    out_dir = settings.experiments_dir / f"sp500_{CONFIG.content_hash()}"
    out = run_backtest(
        source,
        CONFIG,
        start=START,
        end=END,
        cache_dir=settings.cache_dir / "sp500",
        out_dir=out_dir,
        n_shuffles=50,
        data_label="S&P 500 real data",
    )

    stats, shuf = out["stats"], out["shuffle"]
    print(f"universe  : {out['universe_size']} names")
    print(f"window    : {out['equity'].index.min().date()} → {out['equity'].index.max().date()}"
          f"  ({len(out['equity'])} trading days)")
    print(f"CAGR      : {stats['cagr']:+.2%}")
    print(f"Sharpe    : {stats['sharpe']:.2f}")
    print(f"MaxDD     : {stats['max_drawdown']:.2%}")
    print(f"cost drag : {stats['cost_drag']:.2%}")
    print(f"IC (mean) : {out['ic_mean']:+.4f}   IC-IR: {out['ic_ir']:.2f}")
    print(f"shuffle p : {shuf.p_value:.3f}  ({'signal' if shuf.p_value < 0.05 else 'indistinct from noise'})")
    print(f"report    : {out['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
