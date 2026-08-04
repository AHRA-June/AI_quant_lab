"""Natural language → strategy config via an LLM (F2.1).

The LLM's only job is to emit the YAML 2-layer config; the whitelist parser is
the safety boundary, so a malformed or unsafe expression is rejected here rather
than trusted. Generation validates the returned alpha by compiling it, and
retries once with the error fed back.

The LLM client is abstracted behind :class:`LLMClient` so the generator is
testable without network or API keys. :class:`AnthropicClient` is the real
implementation (lazy ``anthropic`` import; install with ``pip install '.[llm]'``).
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from quantlab.dsl.config import StrategyConfig
from quantlab.dsl.parser import DslError
from quantlab.factors import primitives as P

DEFAULT_MODEL = "claude-opus-5"

_FIELDS = ("open", "high", "low", "close", "volume", "value")


def build_system_prompt() -> str:
    """System prompt describing the DSL grammar and the exact operator set."""
    ops = ", ".join(sorted(P.OPERATORS))
    fields = ", ".join(_FIELDS)
    return f"""You translate a natural-language KRX stock strategy idea into a factor DSL config.

Output ONLY a YAML document with exactly three keys — no prose, no code fences:

alpha: "<expression>"
universe: {{market: [KOSPI, KOSDAQ], top_mktcap: 300, min_turnover: 5e8}}
portfolio: {{n_positions: 20, weighting: equal, rebalance: weekly}}

The `alpha` expression is a cross-sectional factor; higher value = more attractive to hold long.

Rules for `alpha`:
- Allowed fields (panels, dates x tickers): {fields}
- Allowed operators ONLY: {ops}
- Allowed arithmetic: + - * / and unary minus. Numeric literals allowed.
- ts_* operators look BACKWARD in time; rank/cs_* are cross-sectional at one date.
- You may NOT use attributes, method calls, indexing, or any function not listed above.
  (No `.shift()`, `.rolling()`, comparisons, or Python builtins.)
- The expression must evaluate to a panel — wrap raw comparisons in rank(...) etc.

Operator reference:
- rank(x): cross-sectional percentile rank [0,1]
- ts_mean/ts_std/ts_min/ts_max/ts_rank/ts_zscore(x, n): trailing n-day window
- ts_sum(x, n): trailing n-day sum
- delay(x, n): value n days ago;  delta(x, n): x - delay(x, n);  returns(x, n): x/delay(x,n) - 1
- scale(x, a=1): normalize row abs-sum to a;  cs_demean/cs_zscore(x): cross-sectional

`portfolio.weighting` is `equal` or `proportional`; `rebalance` is daily/weekly/monthly.

Example — "buy recent losers with rising volume":
alpha: "rank(-returns(close, 5)) * rank(ts_mean(volume, 5) / ts_mean(volume, 20))"
universe: {{market: [KOSPI, KOSDAQ], top_mktcap: 300, min_turnover: 5e8}}
portfolio: {{n_positions: 20, weighting: equal, rebalance: weekly}}
"""


@runtime_checkable
class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str:
        """Return the model's text completion for the given prompts."""
        ...


class AnthropicClient:
    """Real LLM client backed by the Anthropic API."""

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 2000) -> None:
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str) -> str:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - env dependent
            raise ImportError(
                "anthropic is required for LLM generation. Install: pip install '.[llm]'"
            ) from exc
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


_FENCE = re.compile(r"^```(?:ya?ml)?\s*|\s*```$", re.MULTILINE)


def _extract_yaml(text: str) -> str:
    """Strip Markdown code fences if the model added them."""
    return _FENCE.sub("", text).strip()


class StrategyGenerator:
    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self.system = build_system_prompt()

    def generate(self, idea: str, *, max_retries: int = 1) -> StrategyConfig:
        """Natural-language idea → validated :class:`StrategyConfig`.

        Retries once, feeding the validation error back to the model, before
        giving up. Raises :class:`DslError`/``ValueError`` if still invalid.
        """
        user = f"Strategy idea:\n{idea}"
        last_error: Exception | None = None
        for _ in range(max_retries + 1):
            raw = _extract_yaml(self.client.complete(self.system, user))
            try:
                return StrategyConfig.from_yaml(raw)
            except (DslError, ValueError) as exc:
                last_error = exc
                user = (
                    f"Strategy idea:\n{idea}\n\n"
                    f"Your previous output was invalid: {exc}\n"
                    f"Previous output was:\n{raw}\n\n"
                    f"Return a corrected YAML config that fixes this error."
                )
        raise DslError(f"LLM failed to produce a valid strategy: {last_error}")
