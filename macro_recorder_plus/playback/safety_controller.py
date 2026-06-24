from __future__ import annotations

import threading


class SafetyController:
    def __init__(self, *, corner_failsafe: bool = True) -> None:
        self.corner_failsafe = corner_failsafe
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def reset(self) -> None:
        self.stop_event.clear()

    def should_stop(self, cursor_position: tuple[int, int] | None = None) -> bool:
        if self.stop_event.is_set():
            return True
        if self.corner_failsafe and cursor_position in {(0, 0), (0, 1), (1, 0)}:
            self.stop_event.set()
            return True
        return False
