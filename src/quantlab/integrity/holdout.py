"""Holdout vault (F7.5).

The final out-of-sample period must be untouchable by the ordinary research
loop — otherwise it silently degrades into just more in-sample data. This is
enforced by *structure*, not discipline (PRD §0):

* :meth:`HoldoutVault.guard` is called by the normal data path and **raises** if
  a requested date range overlaps the locked holdout window.
* The only way in is :meth:`HoldoutVault.unlock`, which appends an immutable
  audit record (strategy hash, timestamp, running access count) before handing
  over the window. A second unlock for the same strategy emits a warning — the
  access count is visible, so peeking is on the record.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from quantlab.types import as_date


class HoldoutAccessError(RuntimeError):
    """Raised when the normal pipeline touches the locked holdout window."""


@dataclass(frozen=True)
class HoldoutWindow:
    start: date
    end: date

    def overlaps(self, start: date, end: date) -> bool:
        return not (end < self.start or start > self.end)


class HoldoutVault:
    def __init__(
        self,
        holdout_start: str | date,
        holdout_end: str | date,
        audit_path: str | Path,
    ) -> None:
        self.window = HoldoutWindow(as_date(holdout_start), as_date(holdout_end))
        self.audit_path = Path(audit_path)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def guard(self, start: str | date, end: str | date) -> None:
        """Assert a normal-path date range does not touch the holdout."""
        s, e = as_date(start), as_date(end)
        if self.window.overlaps(s, e):
            raise HoldoutAccessError(
                f"date range [{s}..{e}] overlaps locked holdout "
                f"[{self.window.start}..{self.window.end}]; use unlock() deliberately."
            )

    def _access_count(self, strategy_hash: str) -> int:
        return sum(1 for r in self._audit() if r["strategy_hash"] == strategy_hash)

    def _audit(self) -> list[dict]:
        if not self.audit_path.exists():
            return []
        with self.audit_path.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def unlock(self, strategy_hash: str, reason: str) -> HoldoutWindow:
        """Deliberately access the holdout window, recording it in the audit log.

        Returns the window (the caller loads data for it explicitly). Warns if
        this strategy has accessed the holdout before.
        """
        prior = self._access_count(strategy_hash)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "strategy_hash": strategy_hash,
            "reason": reason,
            "access_index": prior + 1,
            "window": [self.window.start.isoformat(), self.window.end.isoformat()],
        }
        with self.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

        if prior >= 1:
            warnings.warn(
                f"holdout accessed {prior + 1}x for strategy {strategy_hash} — "
                "repeated peeking contaminates the out-of-sample test.",
                stacklevel=2,
            )
        return self.window
