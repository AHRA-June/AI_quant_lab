"""Reproducibility bundle (PRD success metric: re-run → 100% identical result).

Every run writes a ``bundle.json`` capturing exactly what it takes to reproduce it:
the inputs, the fixed seeds, the tool/dep versions, and a **fingerprint** of the
result (a hash of the headline metrics). "재현 검증" re-runs from the bundle and
checks the fingerprint matches.

Guarantee scope (honest):
- **synthetic** runs are fully deterministic (fixed synthetic_market + shuffle
  seeds) → auto-reproducible here, offline.
- **csv / krx / nl / screen** depend on external data (a file, the vendor, or an
  LLM). Their bundle records everything, but auto-verification is off — pinning
  the exact data is a documented next step. The fingerprint still lets you check
  reproduction by hand once the data is pinned.
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

SEEDS = {"synthetic_market": 42, "shuffle": 0}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _versions() -> dict:
    import numpy
    import pandas

    try:
        from importlib.metadata import version
        qv = version("quantlab")
    except Exception:  # noqa: BLE001
        qv = "unknown"
    return {"quantlab": qv, "python": platform.python_version(),
            "pandas": pandas.__version__, "numpy": numpy.__version__}


def result_fingerprint(out: dict) -> str:
    """Stable 16-hex digest of the headline metrics (excludes the cumulative
    trial count, which changes every run)."""
    s = out["stats"]
    key = [round(float(s["total_return"]), 8), round(float(s["cagr"]), 8),
           round(float(s["sharpe"]), 8), round(float(s["max_drawdown"]), 8),
           round(float(out["shuffle"].p_value), 8)]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]


def write_bundle(run_dir, *, kind: str, reproducible: bool, inputs: dict, out: dict,
                 reason: str = "") -> dict:
    bundle = {
        "created_at": _now_iso(),
        "version": _versions(),
        "kind": kind,
        "reproducible": reproducible,
        "reason": reason,
        "seeds": SEEDS,
        "inputs": inputs,
        "fingerprint": result_fingerprint(out),
        "verification": None,
    }
    Path(run_dir, "bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle


def read_bundle(store, run_id: str) -> dict | None:
    p = store.base / "runs" / run_id / "bundle.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def reproduce_run(store, run_id: str) -> dict:
    """Re-run a reproducible (synthetic) run from its bundle and compare fingerprints.

    Recomputes into a throwaway trial log so the real trial count isn't polluted,
    stamps the verdict back into ``bundle.json``, and returns the verification dict.
    """
    import tempfile

    from quantlab.demo import STRATEGIES, _evaluate, synthetic_market
    from quantlab.factors.portfolio import top_n_long_only

    bundle = read_bundle(store, run_id)
    if bundle is None:
        raise ValueError("번들이 없습니다")
    if not bundle.get("reproducible"):
        raise ValueError("이 실행은 자동 재현 대상이 아닙니다 (외부 데이터 의존)")

    inp = bundle["inputs"]
    close, volume = synthetic_market()
    fn, needs_vol = STRATEGIES[inp["strategy"]]
    alpha = fn(close, volume) if needs_vol else fn(close)
    weights = top_n_long_only(alpha, n_positions=int(inp["n_positions"]))
    tmp = Path(tempfile.mkdtemp()) / "trials.jsonl"
    out = _evaluate(alpha, weights, close, tmp, int(inp["n_shuffles"]), label=inp["strategy"])

    repro_fp = result_fingerprint(out)
    verification = {"matches": repro_fp == bundle["fingerprint"],
                    "reproduced_fingerprint": repro_fp, "checked_at": _now_iso()}
    bundle["verification"] = verification
    Path(store.base, "runs", run_id, "bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return verification
