from __future__ import annotations

import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager


class CallLog:
    """Latency of model calls, aligned with accepted placements.

    A turn starts in ``choose`` and ends only when that call returns. The next
    turn keeps the total if ``errors`` did not grow. ``finish`` keeps the last
    turn only when another accepted placement is still unaccounted for.
    """

    def __init__(self) -> None:
        self._accepted: list[dict[str, int] | None] = []
        self._pending: dict[str, int] | None = None
        self._returned = False
        self._error_count = 0
        self._latency_ms = 0.0
        self._called = False

    def start_turn(self, errors: Sequence[str]) -> None:
        if self._returned:
            self._commit(len(errors) == self._error_count)
        self._error_count = len(errors)
        self._latency_ms = 0.0
        self._called = False
        self._returned = False

    def add(self, elapsed_seconds: float) -> None:
        self._called = True
        self._latency_ms += elapsed_seconds * 1000

    def end_turn(self) -> None:
        self._pending = (
            {"latency_ms": round(self._latency_ms)} if self._called else None
        )
        self._returned = True

    def finish(self, accepted_placements: int) -> list[dict[str, int] | None]:
        if self._returned:
            self._commit(len(self._accepted) < accepted_placements)
        if len(self._accepted) != accepted_placements:
            raise RuntimeError(
                f"recorded {len(self._accepted)} calls for "
                f"{accepted_placements} placements"
            )
        return list(self._accepted)

    def _commit(self, accepted: bool) -> None:
        if accepted:
            self._accepted.append(self._pending)
        self._returned = False


@contextmanager
def timed(log: CallLog) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        log.add(time.perf_counter() - start)
