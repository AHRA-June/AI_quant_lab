"""Target-weight backtest engine (F4).

Design (PRD §질문1): the strategy produces a **target-weight matrix**; the
engine turns weights → fills, costs, and an equity curve. Long-only, daily,
fully-invested-or-cash. Implemented as an explicit day loop (vectorized across
tickers within each day) so every number is hand-checkable — the golden-value
test (F4.7a) depends on this exactness. T≈2500 iterations is negligible.

Accounting model
----------------
* **t+1 execution (F4.3):** target weights formed from data through the signal
  date are ``shift(execution_lag)``-ed, so a signal at ``t`` is only *held*
  (earns return) from ``t+lag`` onward. No look-ahead.
* **Drift:** between rebalances, held weights drift with realized returns;
  turnover is measured against the drifted book, not the raw target, so we
  don't over-charge cost.
* **Cost (F4.2):** ``(buys+sells)·(commission+slippage) + sells·sell_tax``,
  applied multiplicatively to equity on the rebalance day.
* Weights may sum to ``≤ 1``; the remainder is cash earning 0.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantlab.config import CostModel
from quantlab.backtest.result import BacktestResult


def simple_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Daily simple returns from an (adjusted) price panel; first row → 0."""
    return prices.pct_change().fillna(0.0)


class BacktestEngine:
    def __init__(self, cost: CostModel | None = None, execution_lag: int = 1) -> None:
        self.cost = cost or CostModel()
        if execution_lag < 1:
            raise ValueError("execution_lag must be >= 1 to avoid look-ahead")
        self.execution_lag = execution_lag

    def run(self, target_weights: pd.DataFrame, returns: pd.DataFrame) -> BacktestResult:
        """Simulate holding ``target_weights`` against ``returns``.

        Both frames are dates × tickers and are aligned to their intersection.
        """
        tickers = target_weights.columns.intersection(returns.columns)
        dates = returns.index
        rets = returns.reindex(index=dates, columns=tickers).fillna(0.0)

        # Weights effective (held) from lag days after the signal; persist between.
        desired = (
            target_weights.reindex(columns=tickers)
            .reindex(index=dates)
            .shift(self.execution_lag)
            .ffill()
            .fillna(0.0)
        )

        R = rets.to_numpy()
        D = desired.to_numpy()
        n_days = len(dates)

        comm, slip = self.cost.commission_bps, self.cost.slippage_bps
        tax = self.cost.sell_tax_bps

        w = np.zeros(len(tickers))
        port_r = np.zeros(n_days)
        cost_frac = np.zeros(n_days)
        turnover = np.zeros(n_days)
        held = np.zeros((n_days, len(tickers)))

        for d in range(n_days):
            target = D[d]
            trade = target - w
            buys = np.clip(trade, 0.0, None).sum()
            sells = np.clip(-trade, 0.0, None).sum()
            turnover[d] = buys + sells
            cost_frac[d] = (
                (buys + sells) * (comm + slip) + sells * tax
            ) / 1e4

            w = target                      # post-trade held weights
            held[d] = w
            r = R[d]
            pr = float(w @ r)               # cash (1 - sum w) earns 0
            port_r[d] = pr

            # drift into next day
            denom = 1.0 + pr
            if denom != 0.0:
                w = w * (1.0 + r) / denom

        gross_ret = pd.Series(port_r, index=dates)
        cost_s = pd.Series(cost_frac, index=dates)
        net_ret = (1.0 + gross_ret) * (1.0 - cost_s) - 1.0

        return BacktestResult(
            equity=(1.0 + net_ret).cumprod(),
            gross_equity=(1.0 + gross_ret).cumprod(),
            returns=net_ret,
            turnover=pd.Series(turnover, index=dates),
            cost=cost_s,
            weights=pd.DataFrame(held, index=dates, columns=tickers),
        )
