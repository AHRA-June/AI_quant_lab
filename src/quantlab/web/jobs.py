"""In-process background job queue for backtests.

A backtest on real data can take a while; running it inside the request handler
would block the response and freeze the dashboard. This queue hands the work to a
small thread pool and returns a job id immediately — the page polls job status and
the finished run appears when it's done.

Deliberately dependency-free (no Redis/Celery): a ``ThreadPoolExecutor`` plus a
thread-safe job table. Scope: single process, best-effort, jobs are in-memory
(a restart forgets in-flight jobs — fine for a research tool). CPU-bound pandas
work is GIL-bound, so this buys responsiveness (the request thread is freed), not
true parallelism; a process pool would be the next step if throughput matters.
"""

from __future__ import annotations

import itertools
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    id: str
    kind: str                       # "synthetic" | "csv" | "compare"
    label: str
    status: str                     # "queued" | "running" | "done" | "failed"
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    error: Optional[str] = None
    run_id: Optional[str] = None    # resulting RunRecord id (backtests only)

    @property
    def active(self) -> bool:
        return self.status in ("queued", "running")


class JobQueue:
    """Submit callables; track their lifecycle. Thread-safe."""

    def __init__(self, max_workers: int = 2) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ql-job")
        self._jobs: "dict[str, Job]" = {}
        self._futures: "dict[str, object]" = {}
        self._lock = threading.Lock()
        self._ids = itertools.count(1)

    def submit(self, kind: str, label: str, target: Callable[[], Optional[str]]) -> Job:
        """Enqueue ``target`` (returns an optional run id) and return its Job."""
        with self._lock:
            job = Job(id=f"job-{next(self._ids):04d}", kind=kind, label=label,
                      status="queued", created_at=_now_iso())
            self._jobs[job.id] = job
        self._futures[job.id] = self._pool.submit(self._run, job, target)
        return job

    def cancel(self, job_id: str) -> bool:
        """Cancel a job that has not started yet. Running jobs can't be interrupted."""
        fut = self._futures.get(job_id)
        if fut is None or not fut.cancel():     # cancel() is False once running/done
            return False
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.status = "cancelled"
                job.finished_at = _now_iso()
        return True

    def _run(self, job: Job, target: Callable[[], Optional[str]]) -> None:
        with self._lock:
            job.status = "running"
            job.started_at = _now_iso()
        try:
            run_id = target()
            with self._lock:
                job.run_id = run_id
                job.status = "done"
        except Exception as exc:  # noqa: BLE001 — surface the failure on the job
            with self._lock:
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                job.finished_at = _now_iso()

    def list(self) -> list[Job]:
        """All jobs, newest first."""
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.id, reverse=True)

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.active)

    def as_dicts(self) -> list[dict]:
        return [asdict(j) for j in self.list()]

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
