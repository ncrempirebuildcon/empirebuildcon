"""`empire-worker`: the long-running worker loop for paid, always-on hosting (D-010).

On free hosting this process is NOT run; Cloud Scheduler calls `/api/v1/internal/outbox/drain`
every 15 minutes instead. Both paths use the same functions in integrations/outbox_drain.py.

Each tick runs the schedule tick (scheduled pages, offer start/end), drains due events, then
runs the daily clean-up when it is due. SIGTERM/SIGINT finish
the current tick and exit cleanly (Cloud Run and Docker send SIGTERM before stopping).
"""

from __future__ import annotations

import signal
import threading
from types import FrameType

from empire_api.config import get_settings
from empire_api.integrations.outbox_drain import drain, maybe_cleanup, run_tick_safely
from empire_api.logs import configure_logging, get_logger
from empire_api.observability import init_sentry

log = get_logger(__name__)


def run(stop: threading.Event, interval_seconds: int) -> None:
    while not stop.is_set():
        try:
            run_tick_safely()
            result = drain()
            if result.processed or result.failed:
                log.info("worker_drained", processed=result.processed, failed=result.failed)
            maybe_cleanup()
        except Exception:  # WHY: keep the loop alive; Sentry and the log get details
            log.exception("worker_tick_failed")
        stop.wait(interval_seconds)


def main() -> None:
    settings = get_settings()
    configure_logging()
    init_sentry(settings, component="worker")
    stop = threading.Event()

    def _handle(signum: int, frame: FrameType | None) -> None:
        log.info("worker_stopping", signal=signum)
        stop.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    log.info("worker_started", interval_seconds=settings.worker_drain_interval_seconds)
    run(stop, settings.worker_drain_interval_seconds)


if __name__ == "__main__":
    main()
