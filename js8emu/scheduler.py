from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

log = logging.getLogger("js8emu.scheduler")


class Scheduler:
    """
    Very small helper to run delayed tasks without blocking the selector loop.
    Uses threads as per your chosen concurrency model.
    """

    def __init__(self) -> None:
        self._closed = threading.Event()
        self._threads: list[threading.Thread] = []

    def close(self) -> None:
        self._closed.set()
        for t in list(self._threads):
            t.join(timeout=1.0)

    def run_in_thread(self, fn: Callable[[], None], name: str) -> None:
        if self._closed.is_set():
            return

        t = threading.Thread(target=self._wrap(fn), name=name, daemon=True)
        self._threads.append(t)
        t.start()

    def sleep(self, seconds: float) -> bool:
        """Returns False if scheduler closed while sleeping."""
        if seconds <= 0:
            return not self._closed.is_set()
        end = time.time() + seconds
        while time.time() < end:
            if self._closed.is_set():
                return False
            time.sleep(min(0.05, end - time.time()))
        return not self._closed.is_set()

    def _wrap(self, fn: Callable[[], None]) -> Callable[[], None]:
        def inner() -> None:
            try:
                fn()
            except Exception:
                log.exception("Scheduled task crashed")
        return inner
