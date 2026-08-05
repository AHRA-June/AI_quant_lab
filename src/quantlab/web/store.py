"""Run store — an append-only registry of dashboard backtests.

Each triggered run persists one :class:`RunRecord` (summary metrics + integrity
verdict + a pointer to its self-contained HTML report) as a line of JSON. This is
deliberately the same newline-delimited-JSON shape as the trial log: append-safe,
greppable, never rewritten. The heavy artifacts (the report) live on disk beside
it; the record only stores the relative path.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RunRecord:
    id: str
    created_at: str
    strategy: str
    source: str                     # "synthetic" for now; "csv"/"krx" later
    n_positions: int
    # headline metrics (net of cost)
    cagr: float
    sharpe: float
    max_drawdown: float
    total_return: float
    # research-integrity verdict
    shuffle_p: float
    survives: bool                  # shuffle control passed (p < 0.05)
    trials_logged: int
    report_file: str                # path relative to the runs directory

    @staticmethod
    def new_id(created_at: str, strategy: str) -> str:
        # short, stable, human-glanceable: <utc-compact>-<strategy>
        stamp = created_at.replace("-", "").replace(":", "").replace("+0000", "").replace("T", "-")
        return f"{stamp}-{strategy}"[:64]


class RunStore:
    """Filesystem-backed registry: ``runs.jsonl`` + per-run report directories."""

    def __init__(self, base_dir: str | Path) -> None:
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.index = self.base / "runs.jsonl"

    def run_dir(self, run_id: str) -> Path:
        d = self.base / "runs" / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def append(self, record: RunRecord) -> None:
        with self.index.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")

    def list(self) -> list[RunRecord]:
        """All runs, newest first."""
        if not self.index.exists():
            return []
        out: list[RunRecord] = []
        for line in self.index.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(RunRecord(**json.loads(line)))
        out.reverse()
        return out

    def get(self, run_id: str) -> RunRecord | None:
        for r in self.list():
            if r.id == run_id:
                return r
        return None

    def report_path(self, run_id: str) -> Path | None:
        rec = self.get(run_id)
        if rec is None:
            return None
        p = self.base / "runs" / run_id / rec.report_file
        return p if p.exists() else None
