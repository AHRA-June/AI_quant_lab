"""Automatic trial logging (F7.1).

Every backtest run — **including failures** — must be recorded, because the
multiple-testing correction (DSR) is only meaningful if the trial count is
complete. The logger is append-only and has no "off" switch by design: the run
path wraps each experiment in :meth:`TrialLog.run`, which records an outcome
whether the body succeeds or raises.

Storage is newline-delimited JSON (one record per line) so the log is
append-safe, greppable, and never rewritten.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrialLog:
    def __init__(self, path: str | Path, clock: Callable[[], str] = _utc_now) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock

    def _append(self, record: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def record(
        self,
        config_hash: str,
        status: str,
        *,
        metrics: dict | None = None,
        error: str | None = None,
        meta: dict | None = None,
    ) -> None:
        self._append(
            {
                "ts": self._clock(),
                "config_hash": config_hash,
                "status": status,
                "metrics": metrics or {},
                "error": error,
                "meta": meta or {},
            }
        )

    @contextmanager
    def run(self, config_hash: str, *, meta: dict | None = None) -> Iterator[dict]:
        """Wrap an experiment; record success or failure automatically.

        Yields a mutable dict — populate ``result["metrics"]`` inside the block
        and it is persisted on a clean exit. On exception the failure is logged
        (with the trial still counted) and the exception re-raised.
        """
        result: dict[str, Any] = {"metrics": {}}
        try:
            yield result
        except Exception as exc:  # noqa: BLE001 - we log then re-raise
            self.record(config_hash, "failed", error=f"{type(exc).__name__}: {exc}", meta=meta)
            raise
        else:
            self.record(config_hash, "ok", metrics=result.get("metrics"), meta=meta)

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def count(self) -> int:
        """Total trials logged (success + failure) — the N for DSR."""
        return len(self.load())
