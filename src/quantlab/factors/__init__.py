"""Leak-proof point-in-time factor primitives (M1 core).

This is the *single source of truth* for feature computation: the M2 DSL parser
and the M3 ML feature builder both consume these operators. Every operator is
either **backward-looking in time** (``ts_*``, ``delay``, ``delta``, ``returns``)
or **purely cross-sectional at a single date** (``rank``, ``scale``, ``cs_*``).

Nothing here may look forward. Operators that would touch the full time axis
(full-sample z-score, ``center=True`` rolling, forward shifts) are deliberately
absent — the M2 whitelist AST exposes only what lives in :mod:`.primitives`.
"""

from quantlab.factors import primitives  # noqa: F401
