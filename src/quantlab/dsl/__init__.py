"""Factor DSL (M2).

Natural language → a small, safe factor expression language + portfolio config.
The parser is a **whitelist AST interpreter** over
:data:`quantlab.factors.primitives.OPERATORS`: only registered (backward-looking
or cross-sectional) operators, the six price/volume fields, numeric literals,
and ``+ - * /`` are allowed. Everything else — attribute access, method calls,
subscripts, comprehensions — is rejected, so look-ahead constructs like
``.shift(-1)`` or ``rolling(center=True)`` cannot even be expressed (F2.3/F2.4).
"""

from quantlab.dsl.parser import DslError, compile_alpha, used_fields, used_operators
from quantlab.dsl.config import StrategyConfig

__all__ = [
    "DslError",
    "StrategyConfig",
    "compile_alpha",
    "used_fields",
    "used_operators",
]
