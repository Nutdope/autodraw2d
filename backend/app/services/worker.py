"""All OpenCascade work runs in ONE separate, long-lived worker process.

Why: OpenCascade holds Python's GIL while it computes. In the web process that
froze every other request — including the platform's /api/health probe — for
the whole analysis. On a 0.1-CPU host an upload takes far longer than the 5 s
health-check timeout, so the platform declared the instance dead and restarted
it mid-upload.

With the CAD engine in a worker process the web server stays responsive and
never even loads OpenCascade (it only handles JSON, layout and exports). The
worker:

* is started at boot and kept alive, so OCC's slow import happens once;
* runs one job at a time (``max_workers=1``) — jobs queue, memory stays bounded;
* is recycled after ``MAX_TASKS`` jobs to shed any memory OCC doesn't return;
* is killed and replaced if a job exceeds ``settings.worker_timeout_s`` or the
  process dies (e.g. out of memory on a huge part) — the web server survives and
  the user gets a clear error instead of a restarted server.
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import threading
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any, Callable, Optional

from ..core.config import settings
from ..geometry.loader import StepImportError

log = logging.getLogger("autodraw.worker")

MAX_TASKS = 25  # recycle the worker after this many jobs

_pool: Optional[ProcessPoolExecutor] = None
_pool_lock = threading.Lock()


class WorkerError(StepImportError):
    """The CAD worker died or ran out of time; message is shown to the user."""


def _executor() -> ProcessPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            # spawn: a clean process that never inherits the web server's threads / locks
            _pool = ProcessPoolExecutor(max_workers=1, mp_context=mp.get_context("spawn"),
                                        max_tasks_per_child=MAX_TASKS)
        return _pool


def _reset(pool: ProcessPoolExecutor) -> None:
    """Kill the worker (hung / crashed) and start fresh on the next job."""
    global _pool
    with _pool_lock:
        if _pool is pool:
            _pool = None
    for p in list(getattr(pool, "_processes", {}).values()):
        try:
            p.kill()
        except Exception:
            pass
    pool.shutdown(wait=False, cancel_futures=True)


def run(fn: Callable[..., Any], *args: Any, timeout: Optional[float] = None) -> Any:
    """Run ``fn(*args)`` in the CAD worker and return its result (exceptions re-raised)."""
    if not settings.cad_worker:  # tests / scripts may opt out and run in-process
        return fn(*args)
    pool = _executor()
    try:
        fut = pool.submit(fn, *args)
    except BrokenProcessPool:  # died between jobs: retry once on a fresh worker
        _reset(pool)
        pool = _executor()
        fut = pool.submit(fn, *args)
    try:
        return fut.result(timeout=timeout or settings.worker_timeout_s)
    except FutureTimeout:
        log.warning("CAD job %s timed out, restarting the worker", fn.__name__)
        _reset(pool)
        raise WorkerError(
            "This part took too long to process on this demo server. "
            "Try a simpler part (fewer faces) or remove cosmetic detail."
        ) from None
    except BrokenProcessPool:
        log.warning("CAD worker died during %s (likely out of memory), restarting it", fn.__name__)
        _reset(pool)
        raise WorkerError(
            "This part needs more memory than this demo server has. "
            "Try a simpler part or a single body instead of an assembly."
        ) from None


def warm() -> None:
    """Start the worker and load OpenCascade in it now, not during the first upload."""
    if not settings.cad_worker:
        return
    try:
        run(_load_cad_engine, timeout=600)
        log.info("CAD worker ready")
    except Exception:
        log.exception("CAD worker failed to start")


# ---------------------------------------------------------------------------
# Jobs (top-level functions so they can be pickled into the worker)
# ---------------------------------------------------------------------------
def _load_cad_engine() -> bool:
    import app.pipeline  # noqa: F401  (imports build123d / OCP)

    return True


def analyze_job(step: Path, mesh_out: Path, max_faces, max_solids, orientation):
    from ..pipeline import analyze_part

    return analyze_part(step, mesh_out=mesh_out, max_faces=max_faces, max_solids=max_solids,
                        orientation=orientation)


def section_job(step: Path, analysis, view: str, depth: float, orientation):
    from ..pipeline import compute_section

    return compute_section(step, analysis, view, depth, orientation)
