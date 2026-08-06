"""Rule-based Korean → screen-DSL translator (no LLM required).

The natural-language screen box normally needs an LLM to turn a phrase like
"20일선 위이면서 거래량이 2배 이상" into a boolean :mod:`quantlab.dsl.screen`
expression. Most users don't have an API key, and the direct-expression box is
too technical for them. This module covers the common phrasings with plain
pattern matching so the natural-language box works with **no key at all**.

It is deliberately small and transparent: each recognised clause maps to a
snippet of the whitelisted screen grammar (fields ``open/high/low/close/volume
/value``; ops ``> < >= <=``; ``ts_mean/ts_max/ts_min/delay/returns`` …), and the
clauses are joined by the detected connective (그리고 → ``and``, 또는 → ``or``).
The output is a plain expression string that still goes through
:func:`quantlab.dsl.screen.compile_screen`, so the whitelist stays the single
safety boundary — nothing here can bypass it.

If no clause is recognised the caller gets a friendly, example-laden error via
:class:`NlScreenError` rather than a silent failure.
"""

from __future__ import annotations

import re

__all__ = ["NlScreenError", "nl_to_screen_expr", "SUPPORTED_PHRASES"]


class NlScreenError(ValueError):
    """Raised when a Korean phrase can't be mapped to any screen clause."""


# Human-readable list of what the translator understands, shown in the UI hint
# and in the error message so users can self-correct without reading code.
SUPPORTED_PHRASES = [
    "골든크로스 / 데드크로스",
    "20일선 위 · 60일 이동평균 돌파 (임의 N일)",
    "거래량 급등 · 거래량 3배 이상",
    "20일 신고가 · 60일 신저가",
    "5일 상승 · 10일 하락",
    "최근 20일 10% 이상 상승",
    "연결: 그리고 / 또는 (예: 골든크로스 그리고 거래량 급등)",
]

# A default look-back for phrases that don't name one ("신고가", "거래량 급등").
_DEFAULT_HIGH_LOW_WINDOW = 60
_DEFAULT_VOLUME_WINDOW = 20
_DEFAULT_VOLUME_MULT = 2.0

# Korean digits helper is overkill; users write arabic numerals in practice.
_NUM = r"(\d+(?:\.\d+)?)"


def _clause(text: str) -> str | None:
    """Map one already-split Korean phrase to a screen-DSL snippet, or None."""
    t = text.strip().lower().replace(" ", "")
    if not t:
        return None

    # --- golden / dead cross (moving-average crossovers) -------------------
    if "골든크로스" in t or "goldencross" in t:
        return "ts_mean(close, 5) > ts_mean(close, 20)"
    if "데드크로스" in t or "deadcross" in t:
        return "ts_mean(close, 5) < ts_mean(close, 20)"

    # --- volume spike: "거래량 급등/급증/터짐" or "거래량 N배(이상)" ----------
    if "거래량" in t and any(k in t for k in ("급등", "급증", "터", "폭발", "spike")):
        return (f"volume > ts_mean(volume, {_DEFAULT_VOLUME_WINDOW}) "
                f"* {_DEFAULT_VOLUME_MULT:g}")
    m = re.search(rf"거래량.*?{_NUM}\s*배", t)
    if m:
        mult = float(m.group(1))
        return f"volume > ts_mean(volume, {_DEFAULT_VOLUME_WINDOW}) * {mult:g}"

    # --- moving-average position: "N일선/N일이동평균/N일이평 위·아래·돌파" -----
    m = re.search(rf"{_NUM}\s*일?\s*(?:선|이동평균|이평|말고|ma|이평선)", t)
    if m and any(k in t for k in ("위", "돌파", "상회", "초과", "above", "넘")):
        return f"close > ts_mean(close, {int(float(m.group(1)))})"
    if m and any(k in t for k in ("아래", "하회", "미만", "이하", "below", "밑")):
        return f"close < ts_mean(close, {int(float(m.group(1)))})"

    # --- new high / low: "N일 신고가/최고가", "신저가/최저가" ------------------
    if any(k in t for k in ("신고가", "최고가", "고점", "newhigh")):
        n = _find_window(t, _DEFAULT_HIGH_LOW_WINDOW)
        return f"close >= ts_max(close, {n})"
    if any(k in t for k in ("신저가", "최저가", "저점", "newlow")):
        n = _find_window(t, _DEFAULT_HIGH_LOW_WINDOW)
        return f"close <= ts_min(close, {n})"

    # --- N-day return over a threshold: "최근 20일 10% 이상 상승" --------------
    m = re.search(rf"{_NUM}\s*일.*?{_NUM}\s*%?.*?(상승|올|올라|올랐)", t)
    if m and "%" in t:
        days, pct = int(float(m.group(1))), float(m.group(2))
        return f"returns(close, {days}) > {pct / 100:g}"
    m = re.search(rf"{_NUM}\s*일.*?{_NUM}\s*%?.*?(하락|내|떨어)", t)
    if m and "%" in t:
        days, pct = int(float(m.group(1))), float(m.group(2))
        return f"returns(close, {days}) < {-pct / 100:g}"

    # --- simple N-day up / down (no percentage) ---------------------------
    m = re.search(rf"{_NUM}\s*일.*?(상승|올랐|올라|상향|up)", t)
    if m:
        return f"close > delay(close, {int(float(m.group(1)))})"
    m = re.search(rf"{_NUM}\s*일.*?(하락|내렸|떨어|하향|down)", t)
    if m:
        return f"close < delay(close, {int(float(m.group(1)))})"

    return None


def _find_window(t: str, default: int) -> int:
    """Pull an 'N일' look-back out of a phrase, or fall back to ``default``."""
    m = re.search(rf"{_NUM}\s*일", t)
    return int(float(m.group(1))) if m else default


# Connectives that split a sentence into clauses. "또는/이거나" → or, everything
# else (그리고/및/이면서/이고/,) → and. We detect the *dominant* connective and
# join with it (mixed and/or in one sentence is beyond this rule-based layer).
_OR_TOKENS = ("또는", "이거나", "거나", " or ", "|")
_SPLIT_RE = re.compile(r"그리고|이면서|이고|고,|및|그리고|,|\band\b|\bor\b|또는|이거나|거나")


def nl_to_screen_expr(text: str) -> str:
    """Translate a Korean screen description into a screen-DSL expression.

    Raises :class:`NlScreenError` (with examples) when nothing is recognised, so
    the caller can show the user an actionable message instead of failing mute.
    """
    if not text or not text.strip():
        raise NlScreenError("조건을 입력하세요.")

    use_or = any(tok in text for tok in _OR_TOKENS)
    parts = [p for p in _SPLIT_RE.split(text) if p and p.strip()]
    if not parts:
        parts = [text]

    clauses: list[str] = []
    for part in parts:
        snippet = _clause(part)
        if snippet and snippet not in clauses:
            clauses.append(snippet)

    if not clauses:
        raise NlScreenError(
            "자연어 조건을 이해하지 못했습니다. 이런 표현을 쓸 수 있어요 — "
            + " · ".join(SUPPORTED_PHRASES)
            + ". 예: '20일선 위 그리고 거래량 급등'."
        )

    joiner = " or " if use_or else " and "
    return joiner.join(f"({c})" if use_or else c for c in clauses)
