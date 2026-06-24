from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from macro_recorder_plus.platform.windows_input import keyboard_key_to_name, mouse_button_to_name
from macro_recorder_plus.recorder.event_normalizer import EventNormalizer, NormalizerOptions
from macro_recorder_plus.utilities.timing import monotonic_seconds


@dataclass(slots=True)
class RecordingOptions:
    record_mouse_movement: bool = True
    record_keyboard: bool = True
    record_scroll: bool = True
    mouse_sample_hz: int = 60
    simplification_tolerance: float = 2.0
    ignored_keys: set[str] | None = None


class InputRecorder(QObject):
    actionRecorded = Signal(object)
    started = Signal()
    stopped = Signal()
    pausedChanged = Signal(bool)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.options = RecordingOptions()
        self._keyboard_listener = None
        self._mouse_listener = None
        self._running = False
        self._paused = False
        self._normalizer = EventNormalizer()

    @property
    def running(self) -> bool:
        return self._running

    @Slot(object)
    def start(self, options: RecordingOptions | None = None) -> None:
        if self._running:
            return
        self.options = options or RecordingOptions()
        self.options.ignored_keys = self.options.ignored_keys or set()
        self._normalizer = EventNormalizer(
            NormalizerOptions(
                mouse_sample_hz=self.options.mouse_sample_hz,
                simplification_tolerance=self.options.simplification_tolerance,
            )
        )
        self._normalizer.reset(monotonic_seconds())

        try:
            from pynput import keyboard, mouse

            self._keyboard_listener = keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release)
            self._mouse_listener = mouse.Listener(
                on_move=self._on_mouse_move,
                on_click=self._on_mouse_click,
                on_scroll=self._on_mouse_scroll,
            )
            self._running = True
            self._keyboard_listener.start()
            self._mouse_listener.start()
            self.started.emit()
        except Exception as exc:
            self._running = False
            self.error.emit(str(exc))

    @Slot()
    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for listener in (self._keyboard_listener, self._mouse_listener):
            if listener is not None:
                listener.stop()
        self._keyboard_listener = None
        self._mouse_listener = None
        for action in self._normalizer.flush_mouse_move():
            self.actionRecorded.emit(action)
        self.stopped.emit()

    @Slot()
    def pause_or_resume(self) -> None:
        if not self._running:
            return
        self._paused = not self._paused
        self.pausedChanged.emit(self._paused)

    def _emit_actions(self, actions: list[object]) -> None:
        if self._paused:
            return
        for action in actions:
            self.actionRecorded.emit(action)

    def _on_key_press(self, key: object) -> None:
        if not self._running or not self.options.record_keyboard:
            return
        key_name = keyboard_key_to_name(key)
        if key_name in (self.options.ignored_keys or set()):
            return
        self._emit_actions(self._normalizer.add_keyboard(key_name, "press", monotonic_seconds()))

    def _on_key_release(self, key: object) -> None:
        if not self._running or not self.options.record_keyboard:
            return
        key_name = keyboard_key_to_name(key)
        if key_name in (self.options.ignored_keys or set()):
            return
        self._emit_actions(self._normalizer.add_keyboard(key_name, "release", monotonic_seconds()))

    def _on_mouse_move(self, x: int, y: int) -> None:
        if not self._running or self._paused or not self.options.record_mouse_movement:
            return
        self._emit_actions(self._normalizer.add_mouse_move(x, y, monotonic_seconds()))

    def _on_mouse_click(self, x: int, y: int, button: object, pressed: bool) -> None:
        if not self._running:
            return
        phase = "press" if pressed else "release"
        self._emit_actions(
            self._normalizer.add_mouse_button(x, y, mouse_button_to_name(button), phase, monotonic_seconds())
        )

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if not self._running or not self.options.record_scroll:
            return
        self._emit_actions(self._normalizer.add_scroll(x, y, dx, dy, monotonic_seconds()))
