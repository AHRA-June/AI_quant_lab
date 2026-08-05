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
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

SEEDS = {"synthetic_market": 42, "shuffle": 0}
PIN_DIR = "pinned"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def pin_file(run_dir, src) -> dict:
    """Copy an external input file into the run's ``pinned/`` dir and hash it.

    Returns ``{"name", "sha256", "bytes"}`` — enough to re-run offline and to
    detect if the pinned copy is later tampered with.
    """
    src = Path(src)
    dst_dir = Path(run_dir, PIN_DIR)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    shutil.copyfile(src, dst)
    return {"name": src.name, "sha256": file_sha256(dst), "bytes": dst.stat().st_size}


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


def _reproduce_synthetic(bundle: dict) -> dict:
    import tempfile

    from quantlab.demo import STRATEGIES, _evaluate, synthetic_market
    from quantlab.factors.portfolio import top_n_long_only

    inp = bundle["inputs"]
    close, volume = synthetic_market()
    fn, needs_vol = STRATEGIES[inp["strategy"]]
    alpha = fn(close, volume) if needs_vol else fn(close)
    weights = top_n_long_only(alpha, n_positions=int(inp["n_positions"]))
    tmp = Path(tempfile.mkdtemp()) / "trials.jsonl"
    return _evaluate(alpha, weights, close, tmp, int(inp["n_shuffles"]), label=inp["strategy"])


def _reproduce_csv(store, run_id: str, bundle: dict) -> dict:
    """Re-run a CSV backtest from its **pinned** copy of the source file.

    The pinned CSV lives in ``runs/<id>/pinned/``; we verify its hash still
    matches what the bundle recorded (tamper check) before re-running the exact
    same real-data path into a throwaway dir.
    """
    import tempfile

    from quantlab.data.csv_source import CsvDataSource
    from quantlab.dsl.config import StrategyConfig
    from quantlab.run import run_backtest

    inp = bundle["inputs"]
    pin = Path(store.base, "runs", run_id, PIN_DIR, inp["data_name"])
    if not pin.exists():
        raise ValueError("핀된 데이터 파일이 없습니다")
    if file_sha256(pin) != inp["data_sha256"]:
        raise ValueError("핀된 데이터가 변경되었습니다 (해시 불일치)")

    source = CsvDataSource.from_csv(pin, ticker_col=inp.get("ticker_col", "Name"))
    config = StrategyConfig.from_yaml(inp["config_yaml"])
    tmp = Path(tempfile.mkdtemp())
    return run_backtest(
        source, config,
        start=date.fromisoformat(inp["start"]), end=date.fromisoformat(inp["end"]),
        cache_dir=tmp / "cache", out_dir=tmp / "out",
        n_shuffles=int(inp["n_shuffles"]), data_label=inp.get("data_label", "CSV real data"),
        trials_path=tmp / "trials.jsonl",
    )


def reproduce_run(store, run_id: str) -> dict:
    """Re-run a reproducible run from its bundle and compare fingerprints.

    Synthetic runs recompute from fixed seeds; CSV runs recompute from the pinned
    source file. Both recompute into a throwaway trial log so the real trial count
    isn't polluted, stamp the verdict back into ``bundle.json``, and return the
    verification dict.
    """
    bundle = read_bundle(store, run_id)
    if bundle is None:
        raise ValueError("번들이 없습니다")
    if not bundle.get("reproducible"):
        raise ValueError("이 실행은 자동 재현 대상이 아닙니다 (외부 데이터 의존)")

    kind = bundle.get("kind")
    if kind == "synthetic":
        out = _reproduce_synthetic(bundle)
    elif kind == "csv":
        out = _reproduce_csv(store, run_id, bundle)
    else:
        raise ValueError(f"재현을 지원하지 않는 종류입니다: {kind}")

    repro_fp = result_fingerprint(out)
    verification = {"matches": repro_fp == bundle["fingerprint"],
                    "reproduced_fingerprint": repro_fp, "checked_at": _now_iso()}
    bundle["verification"] = verification
    Path(store.base, "runs", run_id, "bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return verification
