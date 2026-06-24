from __future__ import annotations

import time

from PySide6.QtCore import QObject, Signal, Slot

from macro_recorder_plus.models.environment import RecordedEnvironment, current_environment
from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.platform.windows_monitors import transform_point
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
        recorded_environment: RecordedEnvironment | None = None,
        current_environment_snapshot: RecordedEnvironment | None = None,
        coordinate_mode: str = "exact",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.actions = actions
        self.start_index = max(0, start_index)
        self.speed = max(0.01, speed)
        self.safety = safety or SafetyController()
        self.recorded_environment = recorded_environment or RecordedEnvironment()
        self.current_environment = current_environment_snapshot or current_environment()
        self.coordinate_mode = coordinate_mode
        self._paused = False

    @Slot()
    def run(self) -> None:
        try:
            from pynput import keyboard, mouse

            mouse_controller = mouse.Controller()
            if self.recorded_environment.cursor_start:
                x, y = self.recorded_environment.cursor_start
                mouse_controller.position = transform_point(
                    int(x),
                    int(y),
                    self.recorded_environment,
                    self.current_environment,
                    mode=self.coordinate_mode,
                )
            executor = ActionExecutor(keyboard.Controller(), mouse_controller)
            timer = DriftlessTimer()
            accumulated = 0.0
            for index, action in enumerate(self.actions[self.start_index :], start=self.start_index):
                if self._wait_while_paused_or_stopped(mouse_controller):
                    executor.release_all()
                    self.finished.emit(False, "Playback stopped")
                    return
                if not action.enabled:
                    continue
                accumulated += scaled_delay(action.delay, self.speed)
                if not timer.sleep_until(accumulated, stop_check=lambda: self.safety.should_stop(mouse_controller.position)):
                    executor.release_all()
                    self.finished.emit(False, "Playback stopped")
                    return
                if action.type == ActionType.WAIT:
                    wait_seconds = float(action.params.get("seconds", action.duration or action.delay))
                    time.sleep(scaled_delay(wait_seconds, self.speed))
                else:
                    executor.execute(self._with_transformed_coordinates(action))
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

    def _with_transformed_coordinates(self, action: MacroAction) -> MacroAction:
        if action.type not in {ActionType.MOUSE_MOVE, ActionType.MOUSE_BUTTON, ActionType.SCROLL}:
            return action
        params = dict(action.params)
        if action.type == ActionType.MOUSE_MOVE:
            if "start" in params:
                params["start"] = list(transform_point(*params["start"], self.recorded_environment, self.current_environment, mode=self.coordinate_mode))
            if "end" in params:
                params["end"] = list(transform_point(*params["end"], self.recorded_environment, self.current_environment, mode=self.coordinate_mode))
            if "path" in params:
                params["path"] = [
                    [
                        *transform_point(int(point[0]), int(point[1]), self.recorded_environment, self.current_environment, mode=self.coordinate_mode),
                        point[2],
                    ]
                    for point in params["path"]
                ]
        else:
            if "x" in params and "y" in params:
                params["x"], params["y"] = transform_point(
                    int(params["x"]),
                    int(params["y"]),
                    self.recorded_environment,
                    self.current_environment,
                    mode=self.coordinate_mode,
                )
        return action.with_changes(params=params)
