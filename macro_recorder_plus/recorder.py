from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable

from .keymap import keyboard_key_to_name, mouse_button_to_name
from .model import MacroEvent


class RecorderUnavailable(RuntimeError):
    pass


class MacroRecorder:
    def __init__(
        self,
        on_event: Callable[[MacroEvent], None] | None = None,
        *,
        record_mouse_moves: bool = True,
        mouse_move_interval: float = 0.03,
        ignored_keys: set[str] | None = None,
    ) -> None:
        self.on_event = on_event
        self.record_mouse_moves = record_mouse_moves
        self.mouse_move_interval = mouse_move_interval
        self.ignored_keys = ignored_keys or set()

        self._events: list[MacroEvent] = []
        self._lock = threading.Lock()
        self._running = False
        self._start_time = 0.0
        self._last_move_time = -math.inf
        self._keyboard_listener = None
        self._mouse_listener = None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def events(self) -> list[MacroEvent]:
        with self._lock:
            return list(self._events)

    def start(self) -> None:
        if self._running:
            return

        try:
            from pynput import keyboard, mouse
        except ImportError as exc:
            raise RecorderUnavailable("pynput is required for recording") from exc

        self._events = []
        self._start_time = time.perf_counter()
        self._last_move_time = -math.inf

        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll,
        )

        self._running = True
        try:
            self._keyboard_listener.start()
            self._mouse_listener.start()
        except Exception as exc:
            self.stop()
            raise RecorderUnavailable(str(exc)) from exc

    def stop(self) -> list[MacroEvent]:
        self._running = False
        for listener in (self._keyboard_listener, self._mouse_listener):
            if listener is not None:
                listener.stop()
        self._keyboard_listener = None
        self._mouse_listener = None
        return self.events

    def _elapsed(self) -> float:
        return time.perf_counter() - self._start_time

    def _emit(self, event: MacroEvent) -> None:
        if not self._running:
            return
        with self._lock:
            self._events.append(event)
        if self.on_event is not None:
            self.on_event(event)

    def _on_key_press(self, key: object) -> None:
        key_name = keyboard_key_to_name(key)
        if key_name in self.ignored_keys:
            return
        self._emit(MacroEvent(time=self._elapsed(), device="keyboard", action="press", key=key_name))

    def _on_key_release(self, key: object) -> None:
        key_name = keyboard_key_to_name(key)
        if key_name in self.ignored_keys:
            return
        self._emit(MacroEvent(time=self._elapsed(), device="keyboard", action="release", key=key_name))

    def _on_mouse_move(self, x: int, y: int) -> None:
        if not self.record_mouse_moves:
            return
        elapsed = self._elapsed()
        if elapsed - self._last_move_time < self.mouse_move_interval:
            return
        self._last_move_time = elapsed
        self._emit(MacroEvent(time=elapsed, device="mouse", action="move", x=int(x), y=int(y)))

    def _on_mouse_click(self, x: int, y: int, button: object, pressed: bool) -> None:
        action = "press" if pressed else "release"
        self._emit(
            MacroEvent(
                time=self._elapsed(),
                device="mouse",
                action=action,
                button=mouse_button_to_name(button),
                x=int(x),
                y=int(y),
            )
        )

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        self._emit(
            MacroEvent(
                time=self._elapsed(),
                device="mouse",
                action="scroll",
                x=int(x),
                y=int(y),
                dx=int(dx),
                dy=int(dy),
            )
        )
