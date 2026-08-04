"""Strategy config: the YAML 2-layer format (F2.1).

::

    alpha: "rank(ts_mean(volume, 5) / ts_mean(volume, 20)) * rank(-ts_delta(close, 20))"
    universe: {market: [KOSPI, KOSDAQ], top_mktcap: 300, min_turnover: 5e8}
    portfolio: {n_positions: 20, weighting: equal, rebalance: weekly}

YAML keeps strategies diff-able and comparable across experiments; the alpha
string is validated by the whitelist parser. A content hash of the canonical
config is the reproducibility handle (F2.5).
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from quantlab.dsl.parser import compile_alpha
from quantlab.types import Market, UniverseSpec


class UniverseConfig(BaseModel):
    market: list[Market] = Field(default_factory=lambda: [Market.KOSPI, Market.KOSDAQ])
    top_mktcap: int = 300
    min_turnover: float = 5e8
    turnover_lookback: int = 20

    def to_spec(self) -> UniverseSpec:
        return UniverseSpec(
            markets=tuple(self.market),
            top_mktcap=self.top_mktcap,
            min_turnover=self.min_turnover,
            turnover_lookback=self.turnover_lookback,
        )


class PortfolioConfig(BaseModel):
    n_positions: int = 20
    weighting: Literal["equal", "proportional"] = "equal"
    rebalance: Literal["daily", "weekly", "monthly"] = "weekly"

    @field_validator("n_positions")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("n_positions must be >= 1")
        return v


class StrategyConfig(BaseModel):
    alpha: str
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    portfolio: PortfolioConfig = Field(default_factory=PortfolioConfig)

    @field_validator("alpha")
    @classmethod
    def _alpha_compiles(cls, v: str) -> str:
        compile_alpha(v)  # raises DslError if the expression is invalid
        return v

    # --- serialization -----------------------------------------------------
    @classmethod
    def from_yaml(cls, text: str) -> "StrategyConfig":
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("strategy YAML must be a mapping with an 'alpha' key")
        return cls.model_validate(data)

    def to_yaml(self) -> str:
        return yaml.safe_dump(
            self.model_dump(mode="json"), sort_keys=True, allow_unicode=True
        )

    def content_hash(self) -> str:
        """Stable hash of the canonical config (F2.5 reproducibility handle)."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]
