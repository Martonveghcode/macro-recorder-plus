from __future__ import annotations

import time
import math

from PySide6.QtCore import QObject, Signal, Slot

from macro_recorder_plus.models.environment import RecordedEnvironment, current_environment
from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.platform.windows_monitors import transform_point
from macro_recorder_plus.platform.windows_input import ActionExecutor, find_image_match_for_action
from macro_recorder_plus.playback.safety_controller import SafetyController
from macro_recorder_plus.utilities.timing import scaled_delay

MOUSE_PLAYBACK_HZ = 60


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
            for index, action in enumerate(self.actions[self.start_index :], start=self.start_index):
                if self._wait_while_paused_or_stopped(mouse_controller):
                    executor.release_all()
                    self.finished.emit(False, "Playback stopped")
                    return
                if not action.enabled:
                    continue
                if not self._wait_seconds(scaled_delay(action.delay, self.speed), mouse_controller):
                    executor.release_all()
                    self.finished.emit(False, "Playback stopped")
                    return
                transformed_action = self._with_transformed_coordinates(action)
                if action.type == ActionType.WAIT:
                    wait_seconds = float(action.params.get("seconds", action.duration or action.delay))
                    if not self._wait_seconds(scaled_delay(wait_seconds, self.speed), mouse_controller):
                        executor.release_all()
                        self.finished.emit(False, "Playback stopped")
                        return
                elif action.type == ActionType.MOUSE_MOVE:
                    if not self._play_mouse_move(transformed_action, mouse_controller):
                        executor.release_all()
                        self.finished.emit(False, "Playback stopped")
                        return
                elif action.type == ActionType.IMAGE_CLICK:
                    if not self._play_image_click(transformed_action, executor, mouse_controller):
                        executor.release_all()
                        self.finished.emit(False, "Playback stopped")
                        return
                else:
                    executor.execute(transformed_action)
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

    def _wait_seconds(self, seconds: float, mouse_controller: object) -> bool:
        target = time.perf_counter() + max(0.0, seconds)
        while True:
            if self._paused:
                pause_started = time.perf_counter()
                if self._wait_while_paused_or_stopped(mouse_controller):
                    return False
                target += time.perf_counter() - pause_started
            if self.safety.should_stop(getattr(mouse_controller, "position", None)):
                return False
            remaining = target - time.perf_counter()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, 0.005))

    def _play_mouse_move(self, action: MacroAction, mouse_controller: object) -> bool:
        points = _mouse_move_points(action)
        if not points:
            return True
        start_time = time.perf_counter()
        for x, y, relative_time in _interpolated_mouse_points(points):
            if not self._wait_until(start_time + (relative_time / self.speed), mouse_controller):
                return False
            mouse_controller.position = (int(x), int(y))
        return True

    def _play_image_click(self, action: MacroAction, executor: ActionExecutor, mouse_controller: object) -> bool:
        def stop_check() -> bool:
            if self._paused:
                return self._wait_while_paused_or_stopped(mouse_controller)
            return self.safety.should_stop(getattr(mouse_controller, "position", None))

        match = find_image_match_for_action(action, stop_check=stop_check)
        if match is None:
            if stop_check():
                return False
            if str(action.params.get("on_not_found", "error")) == "skip":
                return True
            raise ValueError(f"Image not found on screen: {action.params.get('image_path', '')}")
        executor.click_image_match(action, match)
        return True

    def _wait_until(self, target: float, mouse_controller: object) -> bool:
        while True:
            if self._paused:
                pause_started = time.perf_counter()
                if self._wait_while_paused_or_stopped(mouse_controller):
                    return False
                target += time.perf_counter() - pause_started
            if self.safety.should_stop(getattr(mouse_controller, "position", None)):
                return False
            remaining = target - time.perf_counter()
            if remaining <= 0:
                return True
            time.sleep(min(remaining, 0.005))

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


def _mouse_move_points(action: MacroAction) -> list[tuple[int, int, float]]:
    raw_path = action.params.get("path") or []
    points: list[tuple[int, int, float]] = []
    for point in raw_path:
        if len(point) >= 3:
            points.append((int(point[0]), int(point[1]), float(point[2])))
    if points:
        return points

    start = action.params.get("start")
    end = action.params.get("end")
    if start and end:
        return [
            (int(start[0]), int(start[1]), float(action.timestamp)),
            (int(end[0]), int(end[1]), float(action.timestamp + action.duration)),
        ]
    if end:
        return [(int(end[0]), int(end[1]), 0.0)]
    return []


def _interpolated_mouse_points(points: list[tuple[int, int, float]]) -> list[tuple[int, int, float]]:
    if len(points) <= 1:
        return points

    first_time = points[0][2]
    output = [(points[0][0], points[0][1], 0.0)]
    for previous, current in zip(points, points[1:], strict=False):
        x1, y1, t1 = previous
        x2, y2, t2 = current
        segment_duration = max(0.0, t2 - t1)
        steps = max(1, math.ceil(segment_duration * MOUSE_PLAYBACK_HZ))
        for step in range(1, steps + 1):
            alpha = step / steps
            x = round(x1 + (x2 - x1) * alpha)
            y = round(y1 + (y2 - y1) * alpha)
            relative_time = max(0.0, (t1 - first_time) + (segment_duration * alpha))
            output.append((x, y, relative_time))
    return output
