from __future__ import annotations

import time
from collections.abc import Callable


def monotonic_seconds() -> float:
    return time.perf_counter()


def scaled_delay(delay: float, speed: float) -> float:
    return max(0.0, float(delay)) / max(0.01, float(speed))


class DriftlessTimer:
    def __init__(self) -> None:
        self._start = monotonic_seconds()

    def sleep_until(self, target_offset: float, *, stop_check: Callable[[], bool] | None = None) -> bool:
        target = self._start + max(0.0, target_offset)
        while True:
            if stop_check is not None and stop_check():
                return False
            remaining = target - monotonic_seconds()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, 0.02))
