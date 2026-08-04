"""LLM strategy generation (M2) — no network, via a fake client."""

import pytest

from quantlab.dsl.config import StrategyConfig
from quantlab.dsl.llm import LLMClient, StrategyGenerator, build_system_prompt
from quantlab.dsl.parser import DslError

GOOD = """
alpha: "rank(-returns(close, 5)) * rank(ts_mean(volume, 5) / ts_mean(volume, 20))"
universe: {market: [KOSPI, KOSDAQ], top_mktcap: 300, min_turnover: 5e8}
portfolio: {n_positions: 20, weighting: equal, rebalance: weekly}
"""

BAD = 'alpha: "close.shift(-1)"\n'  # look-ahead attempt — parser rejects


class ScriptedClient:
    """Returns queued responses in order; records prompts seen."""

    def __init__(self, *responses: str) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append(user)
        return self._responses.pop(0)


def test_generator_produces_valid_config():
    gen = StrategyGenerator(ScriptedClient(GOOD))
    cfg = gen.generate("buy recent losers with rising volume")
    assert isinstance(cfg, StrategyConfig)
    assert cfg.portfolio.n_positions == 20


def test_generator_strips_code_fences():
    fenced = "```yaml\n" + GOOD.strip() + "\n```"
    cfg = StrategyGenerator(ScriptedClient(fenced)).generate("idea")
    assert "returns(close, 5)" in cfg.alpha


def test_generator_retries_on_invalid_then_succeeds():
    client = ScriptedClient(BAD, GOOD)
    cfg = StrategyGenerator(client).generate("idea", max_retries=1)
    assert isinstance(cfg, StrategyConfig)
    assert len(client.calls) == 2
    # the retry prompt carries the validation error back to the model
    assert "invalid" in client.calls[1].lower()


def test_generator_raises_after_exhausting_retries():
    client = ScriptedClient(BAD, BAD)
    with pytest.raises(DslError):
        StrategyGenerator(client).generate("idea", max_retries=1)


def test_scripted_client_satisfies_protocol():
    assert isinstance(ScriptedClient(GOOD), LLMClient)


def test_system_prompt_lists_operators_and_fields():
    sp = build_system_prompt()
    assert "ts_mean" in sp and "rank" in sp and "close" in sp
    # must forbid method-call escape hatches explicitly
    assert ".shift" in sp or "method calls" in sp
