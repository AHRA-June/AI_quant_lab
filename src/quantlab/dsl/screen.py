"""Whitelist compiler for **screen** (filter) expressions.

The alpha DSL (``parser.py``) deliberately forbids comparisons and booleans — a
factor is a continuous score, not a yes/no. A *screen* is the opposite: a boolean
condition over the same primitives, evaluating to a mask (dates × tickers) of
which stocks pass. This module reuses the alpha grammar for the numeric operands
and adds exactly three things on top: comparisons (``> < >= <=``), boolean
combination (``and`` / ``or``), and ``not``.

The whitelist is still the safety boundary — attributes, subscripts, calls to
non-operators, ``==``/``!=``/chained comparisons, and any other construct are
rejected, so an LLM-proposed screen can't reach look-ahead or arbitrary code.

Example::

    close > ts_mean(close, 20) and volume > ts_mean(volume, 20) * 2
"""

from __future__ import annotations

import ast
import functools
from typing import Callable

import pandas as pd

from quantlab.dsl.parser import Context, DslError, _eval as _eval_alpha, _validate as _validate_alpha

ScreenFn = Callable[[Context], pd.DataFrame]

_CMP = {
    ast.Gt: lambda a, b: a > b,
    ast.Lt: lambda a, b: a < b,
    ast.GtE: lambda a, b: a >= b,
    ast.LtE: lambda a, b: a <= b,
}


def _validate_screen(node: ast.AST) -> None:
    """Allow boolean/comparison structure on top of the alpha grammar."""
    if isinstance(node, ast.BoolOp):                 # a and b, a or b (n-ary)
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise DslError("only 'and' / 'or' boolean operators are allowed")
        for v in node.values:
            _validate_screen(v)
        return
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        _validate_screen(node.operand)
        return
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise DslError("chained comparisons (a < b < c) are not allowed")
        if type(node.ops[0]) not in _CMP:
            raise DslError("only > < >= <= comparisons are allowed (not == or !=)")
        _validate_alpha(node.left)                   # operands are alpha expressions
        _validate_alpha(node.comparators[0])
        return
    raise DslError(
        "a screen must be a boolean condition — e.g. "
        "`close > ts_mean(close, 20) and volume > ts_mean(volume, 20) * 2`"
    )


def _eval_screen(node: ast.AST, ctx: Context):
    if isinstance(node, ast.BoolOp):
        vals = [_eval_screen(v, ctx) for v in node.values]
        op = (lambda a, b: a & b) if isinstance(node.op, ast.And) else (lambda a, b: a | b)
        return functools.reduce(op, vals)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return ~_eval_screen(node.operand, ctx)
    if isinstance(node, ast.Compare):
        left = _eval_alpha(node.left, ctx)
        right = _eval_alpha(node.comparators[0], ctx)
        return _CMP[type(node.ops[0])](left, right)
    raise DslError(f"disallowed screen syntax: {type(node).__name__}")  # pragma: no cover


def compile_screen(expr: str) -> ScreenFn:
    """Validate ``expr`` and return ``ctx -> boolean mask panel`` (True = passes)."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise DslError(f"syntax error: {exc.msg}") from exc
    _validate_screen(tree.body)

    def evaluate(ctx: Context) -> pd.DataFrame:
        mask = _eval_screen(tree.body, ctx)
        if not isinstance(mask, pd.DataFrame):
            raise DslError("a screen must evaluate to a mask (DataFrame), not a scalar")
        return mask.fillna(False).astype(bool)

    return evaluate
