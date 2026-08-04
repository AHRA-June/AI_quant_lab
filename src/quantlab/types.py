"""Shared domain types.

Kept dependency-light so every layer can import these without pulling in
pandas-heavy modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Market(str, Enum):
    """KRX markets. Values match pykrx's market identifiers."""

    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"


# Canonical OHLCV column names used everywhere inside quantlab.
# Data sources normalize their (often Korean) columns into these.
OHLCV_COLUMNS = ("open", "high", "low", "close", "volume", "value")


@dataclass(frozen=True)
class SecurityInfo:
    """Point-in-time descriptive info for a listed security.

    Used by the universe filters (DQ.3 / §11). Intentionally minimal — only
    what the exclusion rules need.
    """

    ticker: str
    name: str
    market: Market


@dataclass(frozen=True)
class UniverseSpec:
    """Declarative definition of a point-in-time universe (§11).

    Resolved fresh at every rebalance date so survivorship bias and
    look-ahead cannot leak in via a static constituent list.
    """

    markets: tuple[Market, ...] = (Market.KOSPI, Market.KOSDAQ)
    top_mktcap: int = 300
    min_turnover: float = 5e8  # 20-day median trading value floor (KRW)
    turnover_lookback: int = 20

    def describe(self) -> str:
        mkts = "+".join(m.value for m in self.markets)
        return (
            f"{mkts} top{self.top_mktcap} "
            f"turnover>={self.min_turnover:.0e}/{self.turnover_lookback}d"
        )


def as_date(value: str | date) -> date:
    """Coerce 'YYYY-MM-DD' or 'YYYYMMDD' strings (and date) to a date."""
    if isinstance(value, date):
        return value
    v = value.strip()
    if len(v) == 8 and v.isdigit():  # YYYYMMDD
        return date(int(v[:4]), int(v[4:6]), int(v[6:8]))
    return date.fromisoformat(v)  # YYYY-MM-DD


def to_krx_datestr(value: str | date) -> str:
    """Render a date as pykrx's 'YYYYMMDD' string."""
    return as_date(value).strftime("%Y%m%d")
