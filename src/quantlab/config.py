"""Central configuration (pydantic-validated).

Values can be overridden via environment variables prefixed with ``QUANTLAB_``
or a local ``.env`` file. Keeping cost/universe defaults here means every
experiment shares the same assumptions unless explicitly overridden.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CostModel(BaseSettings):
    """Transaction cost assumptions (F4.2).

    Defaults reflect 2026 KRX figures. Sell-side tax differs by market; we take
    the conservative combined ~0.20% either way and fold it into a round-trip
    estimate together with commission and slippage.
    """

    commission_bps: float = Field(default=1.5, description="per-side commission, basis points")
    sell_tax_bps: float = Field(default=20.0, description="sell-side tax+levy, basis points")
    slippage_bps: float = Field(default=5.0, description="per-side slippage, basis points")

    @property
    def round_trip_bps(self) -> float:
        # buy: commission + slippage; sell: commission + slippage + tax
        return 2 * self.commission_bps + 2 * self.slippage_bps + self.sell_tax_bps


class Settings(BaseSettings):
    """Top-level settings."""

    model_config = SettingsConfigDict(
        env_prefix="QUANTLAB_",
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Filesystem layout
    cache_dir: Path = Field(default=Path("data_cache"))
    experiments_dir: Path = Field(default=Path("experiments"))

    # Price-limit assumption (DQ.6): ±30% daily limit on KRX.
    price_limit_pct: float = 0.30

    cost: CostModel = Field(default_factory=CostModel)

    def ensure_dirs(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.experiments_dir.mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    """Return a fresh Settings instance (reads env/.env each call)."""
    return Settings()
