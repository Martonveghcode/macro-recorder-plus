from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal, Slot

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.platform.windows_input import ActionExecutor
from macro_recorder_plus.playback.safety_controller import SafetyController
from macro_recorder_plus.utilities.timing import DriftlessTimer, scaled_delay


class PlaybackWorker(QObject):
    progress = Signal(int, object)
    status = Signal(str)
    finished = Signal(bool, str)
    error = Signal(str)

    def __init__(
        self,
        actions: list[MacroAction],
        *,
        start_index: int = 0,
        speed: float = 1.0,
        safety: SafetyController | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.actions = actions
        self.start_index = max(0, start_index)
        self.speed = max(0.01, speed)
        self.safety = safety or SafetyController()
        self._paused = False

    @Slot()
    def run(self) -> None:
        try:
            from pynput import keyboard, mouse

            executor = ActionExecutor(keyboard.Controller(), mouse.Controller())
            timer = DriftlessTimer()
            accumulated = 0.0
            for index, action in enumerate(self.actions[self.start_index :], start=self.start_index):
                if self._wait_while_paused_or_stopped(mouse.Controller()):
                    executor.release_all()
                    self.finished.emit(False, "Playback stopped")
                    return
                if not action.enabled:
                    continue
                accumulated += scaled_delay(action.delay, self.speed)
                if not timer.sleep_until(accumulated, stop_check=lambda: self.safety.should_stop(mouse.Controller().position)):
                    executor.release_all()
                    self.finished.emit(False, "Playback stopped")
                    return
                if action.type == ActionType.WAIT:
                    wait_seconds = float(action.params.get("seconds", action.duration or action.delay))
                    time.sleep(scaled_delay(wait_seconds, self.speed))
                else:
                    executor.execute(action)
                self.progress.emit(index, action)
            executor.release_all()
            self.finished.emit(True, "Playback complete")
        except Exception as exc:
            self.error.emit(str(exc))
            self.finished.emit(False, str(exc))

    @Slot()
    def stop(self) -> None:
        self.safety.stop()

    @Slot()
    def pause_or_resume(self) -> None:
        self._paused = not self._paused
        self.status.emit("Playback paused" if self._paused else "Playing")

    def _wait_while_paused_or_stopped(self, mouse_controller: object) -> bool:
        while self._paused:
            if self.safety.should_stop(getattr(mouse_controller, "position", None)):
                return True
            time.sleep(0.05)
        return self.safety.should_stop(getattr(mouse_controller, "position", None))
