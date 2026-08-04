"""Backtest result container."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class BacktestResult:
    """Everything a backtest produces.

    ``equity`` is **net of cost** (the primary curve, F4.6); ``gross_equity``
    strips costs and is used by the engine-validation index-tracking test.
    """

    equity: pd.Series          # net-of-cost equity curve (starts at 1.0)
    gross_equity: pd.Series     # cost-free equity curve
    returns: pd.Series          # net daily portfolio returns
    turnover: pd.Series         # per-day traded fraction (buys + sells)
    cost: pd.Series             # per-day cost as fraction of equity
    weights: pd.DataFrame       # post-trade held weights (dates × tickers)

    @property
    def total_return(self) -> float:
        return float(self.equity.iloc[-1] - 1.0)

    @property
    def avg_turnover(self) -> float:
        return float(self.turnover.mean())

    @property
    def total_cost_drag(self) -> float:
        """Cumulative cost drag: gross final / net final − 1."""
        return float(self.gross_equity.iloc[-1] / self.equity.iloc[-1] - 1.0)
