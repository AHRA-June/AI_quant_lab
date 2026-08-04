"""Security-type exclusion filters (DQ.3).

These strip out instruments that don't belong in a common-stock cross-sectional
universe: preferred shares, SPACs, REITs, ETFs/ETNs. Preferred-stock detection
is heuristic, so we deliberately combine a **ticker-suffix rule with a
name-pattern rule** — either signal is enough — because neither alone is
reliable (PRD §질문1 caveat).

KRX ticker convention: common stock 6-digit codes end in ``0``. Preferred
shares end in a non-zero digit (5/7/9 for old-style, K/L/M-style suffixes for
newer classes), which surfaces as a non-``0`` final character.
"""

from __future__ import annotations

import re

# Name-pattern signals.
_PREFERRED_NAME = re.compile(r"우(B|\d)?$")  # ...우, ...우B, ...우2 등
_SPAC_NAME = re.compile(r"스팩")
_REIT_NAME = re.compile(r"리츠")


def is_preferred(ticker: str, name: str) -> bool:
    """Preferred share? True if the ticker suffix *or* the name says so."""
    suffix_signal = len(ticker) == 6 and ticker[-1] != "0"
    name_signal = bool(_PREFERRED_NAME.search(name))
    return suffix_signal or name_signal


def is_spac(name: str) -> bool:
    return bool(_SPAC_NAME.search(name))


def is_reit(name: str) -> bool:
    return bool(_REIT_NAME.search(name))


def is_common_stock(ticker: str, name: str, *, etf_etn: frozenset[str]) -> bool:
    """True iff ``ticker`` is an ordinary common share eligible for the universe.

    ``etf_etn`` is the set of ETF/ETN tickers as of the relevant date, obtained
    from the data source and passed in (kept out of this pure module so the
    filters stay network-free and unit-testable).
    """
    if ticker in etf_etn:
        return False
    if is_preferred(ticker, name):
        return False
    if is_spac(name):
        return False
    if is_reit(name):
        return False
    return True
