# DSL Vocabulary — derived from hand-crafted strategies (M1 → M2)

> Per the PRD roadmap, the M2 factor DSL's operator set should be **derived from
> real strategies**, not guessed. This tallies the operators actually used by the
> seven hand-crafted strategies in `quantlab/strategies/handcrafted.py`.

## Operator usage across the 7 strategies

| Operator | Kind | Used by | Count |
|----------|------|---------|-------|
| `rank` | cross-sectional | **all 7** | 7 |
| `returns` | time-series (backward) | momentum_12_1, short_term_reversal, low_volatility, momentum_volume_combo | 4 |
| `ts_mean` | time-series | volume_breakout (×2), momentum_volume_combo (×2) | 2 strat |
| unary `-` (negate) | arithmetic | short_term_reversal, low_volatility, zscore_reversion | 3 |
| `/` (divide) | arithmetic | volume_breakout, near_52w_high | 2 |
| `*` (multiply) | arithmetic | momentum_volume_combo | 1 |
| `delay` | time-series | momentum_12_1 | 1 |
| `ts_std` | time-series | low_volatility | 1 |
| `ts_max` | time-series | near_52w_high | 1 |
| `ts_zscore` | time-series | zscore_reversion | 1 |

## Conclusions for the M2 DSL

**Non-negotiable core** (appears everywhere or nearly so):
- `rank` — every single strategy ends in a cross-sectional rank. This is the
  backbone of long-only cross-sectional selection.
- Binary arithmetic `+ - * /` and unary negation — needed to combine and invert
  factors.
- `returns(x, n)` — the most common raw signal.

**Standard time-series set** (each earns its place via ≥1 strategy, and all are
common in the WorldQuant Alpha lineage):
- `delay`, `delta`, `ts_mean`, `ts_std`, `ts_min`, `ts_max`, `ts_rank`, `ts_zscore`

**Cross-sectional set:**
- `rank`, `scale`, `cs_demean`, `cs_zscore`

This is ~15 operators — comfortably inside the ~30 target, leaving room for
`ts_sum`, `ts_corr`, `ts_argmax`, sector-neutralization, etc. as new strategies
demand them. **The rule stays: add an operator only when a real strategy needs
it** (avoid a speculative 30-operator surface that invites overfitting).

**Design confirmations from this exercise:**
1. Every operator used is already in `factors/primitives.py` and is
   backward-looking or single-date — no look-ahead surface to police.
2. The DSL grammar is small: `expr := number | field | op(expr, ...) | expr binop expr`,
   with `field ∈ {close, open, high, low, volume, value}` and `op ∈` the registry
   in `primitives.OPERATORS`.
3. A whitelist AST interpreter over `primitives.OPERATORS` is sufficient — no code
   generation needed (F2.3).
