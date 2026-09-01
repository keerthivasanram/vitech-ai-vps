"""Background writer — telemetry never blocks an engineering request.

The request path only enqueues. A daemon thread drains the queue and writes.

WHEN THE QUEUE IS FULL THE RECORD IS DROPPED, and the drop is counted. That is
the deliberate trade: losing a span costs a line in a trace, whereas blocking
would add database latency to a quotation an engineer is waiting on. Silent loss
would be worse than either, so `dropped` is reported in `/api/admin/metrics`.
"""
import atexit
import queue
import threading
from typing import Any

from . import store

_QUEUE_MAX = 2000

_queue: "queue.Queue[tuple[str, dict]]" = queue.Queue(maxsize=_QUEUE_MAX)
_thread: threading.Thread | None = None
_lock = threading.Lock()
_stats = {"written": 0, "dropped": 0, "errors": 0}

_HANDLERS = {
    "request": store.insert_request,
    "span": store.insert_span,
}


def _drain() -> None:
    while True:
        kind, row = _queue.get()
        if kind == "__stop__":
            _queue.task_done()
            return
        try:
            handler = _HANDLERS.get(kind)
            if handler:
                handler(row)
                _stats["written"] += 1
        except Exception:
            # A telemetry write must never raise into anything. Counted so the
            # failure is visible rather than silent.
            _stats["errors"] += 1
        finally:
            _queue.task_done()


def start() -> None:
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            return
        _thread = threading.Thread(target=_drain, name="obs-writer", daemon=True)
        _thread.start()


def submit(kind: str, row: dict[str, Any]) -> None:
    """Enqueue a record. Never blocks, never raises."""
    try:
        _queue.put_nowait((kind, row))
    except queue.Full:
        _stats["dropped"] += 1
    except Exception:
        _stats["dropped"] += 1


def flush(timeout: float = 5.0) -> bool:
    """Wait for the queue to drain. For tests and shutdown, not the request path."""
    start()
    done = threading.Event()

    def _waiter():
        _queue.join()
        done.set()

    threading.Thread(target=_waiter, daemon=True).start()
    return done.wait(timeout)


def stats() -> dict:
    return {**_stats, "queued": _queue.qsize(), "capacity": _QUEUE_MAX}


@atexit.register
def _shutdown() -> None:
    try:
        flush(2.0)
    except Exception:
        pass
