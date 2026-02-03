from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence

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

    def run_frame_sequence(
        self,
        fragments: Sequence[str],
        frame_time: float,
        *,
        on_wait_start: Callable[[int, str], None] | None = None,
        on_frame_sent: Callable[[int, str], None] | None = None,
        on_abort: Callable[[int, str], None] | None = None,
        send_fragment: Callable[[int, str], None],
    ) -> None:
        """Run a framed transmission sequence.

        Each fragment is sent after a wait of ``frame_time`` seconds.

        This helper exists so callers can implement JS8Call-like timing and
        side-effects (e.g., PTT messages) without blocking the selector loop.

        Args:
            fragments: The fragments to transmit.
            frame_time: Delay before each fragment is sent.
            on_wait_start: Called right before the delay for a fragment starts.
            on_frame_sent: Called immediately after a fragment is sent.
            on_abort: Called if the scheduler is closed while waiting.
            send_fragment: Called to actually deliver each fragment.
        """
        for i, frag in enumerate(fragments):
            if on_wait_start:
                on_wait_start(i, frag)

            if not self.sleep(frame_time):
                if on_abort:
                    on_abort(i, frag)
                return

            send_fragment(i, frag)

            if on_frame_sent:
                on_frame_sent(i, frag)

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
