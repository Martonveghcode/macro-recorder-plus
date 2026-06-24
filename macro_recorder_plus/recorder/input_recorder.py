from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.models.environment import MonitorInfo, current_environment
from macro_recorder_plus.platform.windows_input import keyboard_key_to_name, mouse_button_to_name
from macro_recorder_plus.recorder.event_normalizer import EventNormalizer, NormalizerOptions
from macro_recorder_plus.utilities.key_sequences import normalize_hotkey
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
        self._held_keys: set[str] = set()
        self._last_click: tuple[str, int, int, float] | None = None
        self._monitors: list[MonitorInfo] = []
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
        self._monitors = current_environment().monitors

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

    def _emit_actions(self, actions: list[MacroAction]) -> None:
        if self._paused:
            return
        for action in actions:
            self._annotate_monitor(action)
            self.actionRecorded.emit(action)

    def _annotate_monitor(self, action: MacroAction) -> None:
        if action.type not in {ActionType.MOUSE_MOVE, ActionType.MOUSE_BUTTON, ActionType.SCROLL}:
            return
        x = action.params.get("x")
        y = action.params.get("y")
        if x is None or y is None:
            end = action.params.get("end")
            if end:
                x, y = end[0], end[1]
        if x is None or y is None:
            return
        monitor = self._monitor_for_point(int(x), int(y))
        if monitor:
            action.params["monitor"] = monitor.identifier

    def _monitor_for_point(self, x: int, y: int) -> MonitorInfo | None:
        for monitor in self._monitors:
            bounds = monitor.bounds
            if bounds.left <= x < bounds.right and bounds.top <= y < bounds.bottom:
                return monitor
        return None

    def _on_key_press(self, key: object) -> None:
        if not self._running or not self.options.record_keyboard:
            return
        key_name = keyboard_key_to_name(key)
        if key_name in (self.options.ignored_keys or set()):
            return
        now = monotonic_seconds()
        self._held_keys.add(key_name)
        modifiers = sorted(key for key in self._held_keys if _is_modifier(key))
        if modifiers and not _is_modifier(key_name):
            self._emit_actions(self._normalizer.add_hotkey(normalize_hotkey(modifiers + [key_name]), now))
            return
        self._emit_actions(self._normalizer.add_keyboard(key_name, "press", now))

    def _on_key_release(self, key: object) -> None:
        if not self._running or not self.options.record_keyboard:
            return
        key_name = keyboard_key_to_name(key)
        if key_name in (self.options.ignored_keys or set()):
            return
        self._held_keys.discard(key_name)
        self._emit_actions(self._normalizer.add_keyboard(key_name, "release", monotonic_seconds()))

    def _on_mouse_move(self, x: int, y: int) -> None:
        if not self._running or self._paused or not self.options.record_mouse_movement:
            return
        self._emit_actions(self._normalizer.add_mouse_move(x, y, monotonic_seconds()))

    def _on_mouse_click(self, x: int, y: int, button: object, pressed: bool) -> None:
        if not self._running:
            return
        phase = "press" if pressed else "release"
        now = monotonic_seconds()
        self._emit_actions(
            self._normalizer.add_mouse_button(x, y, mouse_button_to_name(button), phase, now)
        )
        if not pressed:
            button_name = mouse_button_to_name(button)
            if self._is_double_click(button_name, int(x), int(y), now):
                self._emit_actions(self._normalizer.add_mouse_button(x, y, button_name, "double_click", now))
            self._last_click = (button_name, int(x), int(y), now)

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if not self._running or not self.options.record_scroll:
            return
        self._emit_actions(self._normalizer.add_scroll(x, y, dx, dy, monotonic_seconds()))

    def _is_double_click(self, button: str, x: int, y: int, now: float) -> bool:
        if self._last_click is None:
            return False
        last_button, last_x, last_y, last_time = self._last_click
        return button == last_button and abs(x - last_x) <= 4 and abs(y - last_y) <= 4 and now - last_time <= 0.35


def _is_modifier(key_name: str) -> bool:
    return key_name in {"ctrl", "shift", "alt", "win"}
