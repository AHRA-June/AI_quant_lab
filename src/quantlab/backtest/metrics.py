"""Performance metrics (F5.1) and cross-sectional IC (F3.5).

All return-based metrics assume a daily series with ``PERIODS_PER_YEAR``
trading days. Rank IC lives here too so M3's evaluation reuses the same code.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PERIODS_PER_YEAR = 252


def cagr(equity: pd.Series) -> float:
    years = len(equity) / PERIODS_PER_YEAR
    if years <= 0 or equity.iloc[0] <= 0:
        return float("nan")
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)


def ann_vol(returns: pd.Series) -> float:
    return float(returns.std() * np.sqrt(PERIODS_PER_YEAR))


def sharpe(returns: pd.Series, rf: float = 0.0) -> float:
    excess = returns - rf / PERIODS_PER_YEAR
    sd = excess.std()
    if sd == 0:
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(PERIODS_PER_YEAR))


def sortino(returns: pd.Series, rf: float = 0.0) -> float:
    excess = returns - rf / PERIODS_PER_YEAR
    downside = excess[excess < 0]
    dd = np.sqrt((downside**2).mean()) if len(downside) else 0.0
    if dd == 0:
        return float("nan")
    return float(excess.mean() / dd * np.sqrt(PERIODS_PER_YEAR))


def max_drawdown(equity: pd.Series) -> float:
    """Most negative peak-to-trough drawdown (≤ 0)."""
    running_max = equity.cummax()
    dd = equity / running_max - 1.0
    return float(dd.min())


def win_rate(returns: pd.Series) -> float:
    nonzero = returns[returns != 0]
    if nonzero.empty:
        return float("nan")
    return float((nonzero > 0).mean())


def summary(returns: pd.Series, equity: pd.Series, turnover: pd.Series | None = None) -> dict:
    out = {
        "total_return": float(equity.iloc[-1] / equity.iloc[0] - 1),
        "cagr": cagr(equity),
        "ann_vol": ann_vol(returns),
        "sharpe": sharpe(returns),
        "sortino": sortino(returns),
        "max_drawdown": max_drawdown(equity),
        "win_rate": win_rate(returns),
    }
    if turnover is not None:
        out["avg_turnover"] = float(turnover.mean())
    return out


# --- cross-sectional information coefficient (F3.5) ------------------------


def rank_ic(signal: pd.DataFrame, forward_returns: pd.DataFrame) -> pd.Series:
    """Daily cross-sectional Spearman rank IC between signal and forward returns.

    Both are dates × tickers; each date's IC is the rank correlation across the
    names available that day. Returns a per-date Series.
    """
    sig = signal.rank(axis=1)
    fwd = forward_returns.rank(axis=1)
    ics = {}
    for dt in sig.index.intersection(fwd.index):
        a, b = sig.loc[dt], fwd.loc[dt]
        mask = a.notna() & b.notna()
        if mask.sum() >= 2:
            ics[dt] = a[mask].corr(b[mask])
    return pd.Series(ics).sort_index()


def ic_ir(daily_ic: pd.Series) -> float:
    """Information ratio of the IC series: mean(IC) / std(IC)."""
    sd = daily_ic.std()
    if sd == 0 or np.isnan(sd):
        return float("nan")
    return float(daily_ic.mean() / sd)
