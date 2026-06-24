from __future__ import annotations

import threading
from collections.abc import Callable

from .keymap import name_to_keyboard_key, name_to_mouse_button
from .model import Macro, MacroEvent


StatusCallback = Callable[[str], None]
EventCallback = Callable[[MacroEvent, int, int], None]
DoneCallback = Callable[[bool], None]


class PlaybackUnavailable(RuntimeError):
    pass


class MacroPlayer:
    def __init__(
        self,
        *,
        on_status: StatusCallback | None = None,
        on_event: EventCallback | None = None,
        on_done: DoneCallback | None = None,
    ) -> None:
        self.on_status = on_status
        self.on_event = on_event
        self.on_done = on_done
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def play(self, macro: Macro, *, speed: float = 1.0, loops: int = 1) -> None:
        if self.running:
            return
        if not macro.events:
            self._status("Nothing to play")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(macro, max(0.1, float(speed)), max(1, int(loops))),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self, macro: Macro, speed: float, loops: int) -> None:
        completed = False
        try:
            from pynput import keyboard, mouse
        except ImportError as exc:
            self._status("pynput is required for playback")
            self._done(False)
            self._thread = None
            return

        keyboard_controller = keyboard.Controller()
        mouse_controller = mouse.Controller()
        total = len(macro.events) * loops
        index = 0

        try:
            for loop in range(loops):
                previous_time = 0.0
                for event in macro.events:
                    if self._stop_event.is_set():
                        self._status("Playback stopped")
                        self._done(False)
                        return

                    delay = max(0.0, event.time - previous_time) / speed
                    previous_time = event.time
                    if self._stop_event.wait(delay):
                        self._status("Playback stopped")
                        self._done(False)
                        return

                    index += 1
                    self._dispatch(event, keyboard_controller, mouse_controller)
                    if self.on_event is not None:
                        self.on_event(event, index, total)

                self._status(f"Completed loop {loop + 1} of {loops}")
            completed = True
            self._status("Playback complete")
        finally:
            self._done(completed)

    def _dispatch(self, event: MacroEvent, keyboard_controller: object, mouse_controller: object) -> None:
        if event.device == "keyboard":
            if event.key is None:
                return
            key = name_to_keyboard_key(event.key)
            if event.action == "press":
                keyboard_controller.press(key)
            elif event.action == "release":
                keyboard_controller.release(key)
            return

        if event.device != "mouse":
            return

        if event.x is not None and event.y is not None:
            mouse_controller.position = (event.x, event.y)

        if event.action in {"press", "release"} and event.button is not None:
            button = name_to_mouse_button(event.button)
            if event.action == "press":
                mouse_controller.press(button)
            else:
                mouse_controller.release(button)
        elif event.action == "scroll":
            mouse_controller.scroll(event.dx or 0, event.dy or 0)

    def _status(self, message: str) -> None:
        if self.on_status is not None:
            self.on_status(message)

    def _done(self, completed: bool) -> None:
        if self.on_done is not None:
            self.on_done(completed)
