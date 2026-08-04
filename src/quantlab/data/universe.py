"""Point-in-time universe reconstruction (§11).

The universe is rebuilt at each rebalance date ``t`` from the securities that
were *actually listed on t*, so survivorship bias and look-ahead cannot enter
via a static (present-day) constituent list.

Steps at date ``t``:
    1. tickers listed on t across the requested markets  (PIT)
    2. drop preferred / SPAC / REIT / ETF / ETN          (DQ.3)
    3. keep top-N by market cap
    4. liquidity floor: rolling median trading value ≥ threshold

Step 4 needs price history and is skipped (with the candidate set returned
as-is) when no ``PriceStore`` is supplied — useful for tests and for callers
that apply liquidity filtering elsewhere.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from quantlab.data.cache import PriceStore
from quantlab.data.filters import is_common_stock
from quantlab.data.source import DataSource
from quantlab.types import UniverseSpec


class UniverseBuilder:
    def __init__(self, source: DataSource, price_store: PriceStore | None = None) -> None:
        self.source = source
        self.price_store = price_store

    def _eligible_common_stocks(self, on: date, spec: UniverseSpec) -> list[str]:
        etf_etn = frozenset(self.source.get_etf_etn_ticker_list(on))
        eligible: list[str] = []
        for market in spec.markets:
            for ticker in self.source.get_ticker_list(on, market):
                name = self.source.get_ticker_name(ticker, on)
                if is_common_stock(ticker, name, etf_etn=etf_etn):
                    eligible.append(ticker)
        return eligible

    def _top_by_mktcap(self, on: date, spec: UniverseSpec, eligible: list[str]) -> list[str]:
        caps: list[pd.Series] = []
        for market in spec.markets:
            mc = self.source.get_market_cap(on, market)
            caps.append(mc["mktcap"])
        mktcap = pd.concat(caps)
        mktcap = mktcap[mktcap.index.isin(eligible)]
        ranked = mktcap.sort_values(ascending=False)
        return ranked.head(spec.top_mktcap).index.tolist()

    def _liquid_enough(self, on: date, spec: UniverseSpec, candidates: list[str]) -> list[str]:
        if self.price_store is None:
            return candidates
        start = on - timedelta(days=spec.turnover_lookback * 2 + 10)  # calendar pad for trading days
        kept: list[str] = []
        for ticker in candidates:
            raw = self.price_store.get_raw(ticker, start, on)
            recent = raw["value"].tail(spec.turnover_lookback)
            if len(recent) and recent.median() >= spec.min_turnover:
                kept.append(ticker)
        return kept

    def build(self, on: date, spec: UniverseSpec | None = None) -> list[str]:
        """Return the point-in-time universe ticker list for date ``on``."""
        spec = spec or UniverseSpec()
        eligible = self._eligible_common_stocks(on, spec)
        top = self._top_by_mktcap(on, spec, eligible)
        return self._liquid_enough(on, spec, top)
