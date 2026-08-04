"""Whitelist AST parser/interpreter for factor expressions (F2.3/F2.4).

Grammar (informal)::

    expr   := number | field | call | expr binop expr | -expr
    field  := open | high | low | close | volume | value
    call   := opname '(' expr (',' expr | kw=expr)* ')'
    opname := <a name registered in primitives.OPERATORS>
    binop  := + | - | * | /

The parser reuses Python's tokenizer/AST but then **walks the tree against a
strict whitelist**. Any node type outside the grammar (Attribute, Subscript,
Lambda, comprehensions, boolean/compare ops, calls to non-operators, unknown
names) raises :class:`DslError`. Because method calls and attribute access are
unreachable, no look-ahead construct can be written.
"""

from __future__ import annotations

import ast
from typing import Callable

import pandas as pd

from quantlab.factors import primitives as P

ALLOWED_FIELDS = frozenset(("open", "high", "low", "close", "volume", "value"))
_OPERATORS = P.OPERATORS

_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
}

Context = dict[str, pd.DataFrame]
AlphaFn = Callable[[Context], pd.DataFrame]


class DslError(ValueError):
    """Raised when an expression is malformed or uses a disallowed construct."""


def _validate(node: ast.AST) -> None:
    """Recursively assert every node is inside the grammar."""
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)) or isinstance(node.value, bool):
            raise DslError(f"only numeric literals allowed, got {node.value!r}")
        return
    if isinstance(node, ast.Name):
        if node.id not in ALLOWED_FIELDS:
            raise DslError(
                f"unknown name {node.id!r}; fields must be one of {sorted(ALLOWED_FIELDS)}"
            )
        return
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.USub, ast.UAdd)):
            raise DslError(f"unary operator {type(node.op).__name__} not allowed")
        _validate(node.operand)
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _BINOPS:
            raise DslError(f"binary operator {type(node.op).__name__} not allowed (use + - * /)")
        _validate(node.left)
        _validate(node.right)
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _OPERATORS:
            name = getattr(node.func, "id", type(node.func).__name__)
            raise DslError(f"call to {name!r} not allowed; operators: {sorted(_OPERATORS)}")
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                raise DslError("*args not allowed")
            _validate(arg)
        for kw in node.keywords:
            if kw.arg is None:
                raise DslError("**kwargs not allowed")
            _validate(kw.value)
        return
    raise DslError(f"disallowed syntax: {type(node).__name__}")


def _eval(node: ast.AST, ctx: Context):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        try:
            return ctx[node.id]
        except KeyError as exc:
            raise DslError(f"field {node.id!r} missing from evaluation context") from exc
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, ctx)
        return -v if isinstance(node.op, ast.USub) else +v
    if isinstance(node, ast.BinOp):
        return _BINOPS[type(node.op)](_eval(node.left, ctx), _eval(node.right, ctx))
    if isinstance(node, ast.Call):
        fn = _OPERATORS[node.func.id]
        args = [_eval(a, ctx) for a in node.args]
        kwargs = {kw.arg: _eval(kw.value, ctx) for kw in node.keywords}
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # surface operator misuse as a DSL error
            raise DslError(f"{node.func.id}(): {exc}") from exc
    raise DslError(f"disallowed syntax: {type(node).__name__}")  # pragma: no cover


def _parse(expr: str) -> ast.AST:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise DslError(f"syntax error: {exc.msg}") from exc
    _validate(tree.body)
    return tree.body


def compile_alpha(expr: str) -> AlphaFn:
    """Validate ``expr`` and return ``ctx -> alpha panel``.

    Raises :class:`DslError` at compile time for any disallowed construct, so an
    invalid LLM-generated expression is rejected before it can run.
    """
    body = _parse(expr)

    def evaluate(ctx: Context) -> pd.DataFrame:
        result = _eval(body, ctx)
        if not isinstance(result, pd.DataFrame):
            raise DslError("alpha must evaluate to a panel (DataFrame), not a scalar")
        return result

    return evaluate


def used_operators(expr: str) -> set[str]:
    """Operator names referenced by ``expr`` (for auditing/vocabulary tally)."""
    body = _parse(expr)
    return {n.func.id for n in ast.walk(body) if isinstance(n, ast.Call)}


def used_fields(expr: str) -> set[str]:
    """Price/volume fields referenced by ``expr``."""
    body = _parse(expr)
    return {n.id for n in ast.walk(body) if isinstance(n, ast.Name) and n.id in ALLOWED_FIELDS}
