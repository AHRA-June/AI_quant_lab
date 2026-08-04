"""Hand-crafted factor strategies (M1).

Purpose (PRD §roadmap): before building the M2 DSL, write a handful of real
strategies *using the primitives* to discover the common vocabulary the DSL
must express. Every strategy here is a function ``(close[, volume]) -> alpha``
built only from :mod:`quantlab.factors.primitives`. See
``docs/DSL_VOCABULARY.md`` for the operator tally these produce.
"""

from quantlab.strategies.handcrafted import STRATEGIES

__all__ = ["STRATEGIES"]
