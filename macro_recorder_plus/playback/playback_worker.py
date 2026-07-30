from __future__ import annotations

import random
import time

from PySide6.QtCore import QObject, Signal, Slot

from macro_recorder_plus.models.environment import RecordedEnvironment, current_environment
from macro_recorder_plus.models.actions import ActionType, MacroAction, clamp_loop_count
from macro_recorder_plus.models.macro import clamp_macro_loop_count, clamp_macro_loop_delay
from macro_recorder_plus.platform.windows_monitors import clamp_point, transform_point
from macro_recorder_plus.platform.windows_input import (
    ActionExecutor,
    find_image_match_for_action,
    image_movement_points_for_match,
    position_mouse,
)
from macro_recorder_plus.playback.safety_controller import SafetyController
from macro_recorder_plus.utilities.mouse_path import humanized_path_points, interpolated_path_points
from macro_recorder_plus.utilities.timing import scaled_delay

MOUSE_PLAYBACK_HZ = 60


class PlaybackWorker(QObject):
    progress = Signal(int, object)
    preActionProgress = Signal(int, object)
    status = Signal(str)
    playbackContext = Signal(int, object)
    finished = Signal(bool, str)
    error = Signal(str)

    def __init__(
        self,
        actions: list[MacroAction],
        *,
        pre_actions: list[MacroAction] | None = None,
        start_index: int = 0,
        end_index: int | None = None,
        repeat_count: int = 1,
        loop_delay_min: float = 0.0,
        loop_delay_max: float = 0.0,
        speed: float = 1.0,
        respect_action_delays: bool = True,
        initial_image_found: bool | None = None,
        safety: SafetyController | None = None,
        recorded_environment: RecordedEnvironment | None = None,
        current_environment_snapshot: RecordedEnvironment | None = None,
        coordinate_mode: str = "exact",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.actions = actions
        self.pre_actions = pre_actions or []
        self.start_index = max(0, start_index)
        self.limit_to_range = end_index is not None
        self.end_index = len(actions) if end_index is None else min(len(actions), max(self.start_index, end_index))
        self.repeat_count = clamp_macro_loop_count(repeat_count)
        self.loop_delay_min = clamp_macro_loop_delay(loop_delay_min)
        self.loop_delay_max = clamp_macro_loop_delay(loop_delay_max)
        if self.loop_delay_min > self.loop_delay_max:
            self.loop_delay_min, self.loop_delay_max = self.loop_delay_max, self.loop_delay_min
        self.speed = max(0.01, speed)
        self.respect_action_delays = respect_action_delays
        self.initial_image_found = initial_image_found
        self.safety = safety or SafetyController()
        self.recorded_environment = recorded_environment or RecordedEnvironment()
        self.current_environment = current_environment_snapshot or current_environment()
        self.coordinate_mode = coordinate_mode
        self._paused = False
        self._last_image_found: bool | None = None
        self._humanized_mouse_source: tuple[int, int] | None = None
        self._humanized_mouse_destination: tuple[int, int] | None = None

    @Slot()
    def run(self) -> None:
        executor: ActionExecutor | None = None
        try:
            from pynput import keyboard, mouse

            mouse_controller = mouse.Controller()
            executor = ActionExecutor(keyboard.Controller(), mouse_controller)
            range_start = min(self.start_index, len(self.actions))
            range_lower_bound = range_start if self.limit_to_range else 0
            index = range_start
            if self.pre_actions:
                self.status.emit(f"Running {len(self.pre_actions)} pre-action(s) once")
                self._last_image_found = None
                completed, _ = self._play_range(
                    self.pre_actions,
                    0,
                    len(self.pre_actions),
                    0,
                    executor,
                    mouse_controller,
                    self.preActionProgress,
                    context_label="pre-actions",
                )
                if not completed:
                    self.finished.emit(False, "Playback stopped")
                    return
            for macro_loop_index in range(self.repeat_count):
                if self.repeat_count > 1:
                    self.status.emit(f"Playing macro loop {macro_loop_index + 1} of {self.repeat_count}")
                if self._begin_macro_loop(executor, mouse_controller):
                    self.finished.emit(False, "Playback stopped")
                    return
                self._last_image_found = self.initial_image_found if macro_loop_index == 0 else None
                completed, index = self._play_range(
                    self.actions,
                    range_start,
                    self.end_index,
                    range_lower_bound,
                    executor,
                    mouse_controller,
                    self.progress,
                    context_label=f"macro loop {macro_loop_index + 1} of {self.repeat_count}",
                )
                if not completed:
                    self.finished.emit(False, "Playback stopped")
                    return
                if macro_loop_index + 1 < self.repeat_count:
                    loop_delay = random.uniform(self.loop_delay_min, self.loop_delay_max)
                    if loop_delay > 0:
                        self.status.emit(
                            f"Waiting {loop_delay:.2f}s before macro loop {macro_loop_index + 2} of {self.repeat_count}"
                        )
                        if not self._wait_seconds(loop_delay, mouse_controller):
                            self.finished.emit(False, "Playback stopped")
                            return
            self.playbackContext.emit(index, self._last_image_found)
            message = "Playback complete"
            if self.repeat_count > 1:
                message = f"Playback complete ({self.repeat_count} loops)"
            self.finished.emit(True, message)
        except Exception as exc:
            self.error.emit(str(exc))
            self.finished.emit(False, str(exc))
        finally:
            if executor is not None:
                executor.release_all()

    def _begin_macro_loop(self, executor: ActionExecutor, mouse_controller: object) -> bool:
        """Reset transient input state and reproduce the same cursor anchor for every loop."""
        executor.release_all()
        self._clear_humanized_mouse_destination()
        if self._wait_while_paused_or_stopped(mouse_controller):
            return True
        if self.recorded_environment.cursor_start:
            x, y = self.recorded_environment.cursor_start
            target_x, target_y = transform_point(
                int(x),
                int(y),
                self.recorded_environment,
                self.current_environment,
                mode=self.coordinate_mode,
            )
            position_mouse(mouse_controller, target_x, target_y)
        return False

    def _play_range(
        self,
        actions: list[MacroAction],
        start_index: int,
        end_index: int,
        lower_bound: int,
        executor: ActionExecutor,
        mouse_controller: object,
        progress_signal: Signal,
        *,
        context_label: str = "playback",
    ) -> tuple[bool, int]:
        index = start_index
        while lower_bound <= index < end_index:
            action = actions[index]
            next_index = index + 1
            if self._wait_while_paused_or_stopped(mouse_controller):
                return False, index
            if not action.enabled:
                if action.type == ActionType.IMAGE_CLICK:
                    self._last_image_found = None
                if action.type == ActionType.MOUSE_MOVE:
                    self._clear_humanized_mouse_destination()
                index = next_index
                continue
            for _loop_index in range(clamp_loop_count(action.loop_count)):
                if self._wait_while_paused_or_stopped(mouse_controller):
                    return False, index
                action_delay = action.delay if self.respect_action_delays else 0.0
                if not self._wait_seconds(scaled_delay(action_delay, self.speed), mouse_controller):
                    return False, index
                try:
                    transformed_action = self._with_transformed_coordinates(action)
                    if action.type in {ActionType.MOUSE_BUTTON, ActionType.SCROLL}:
                        transformed_action = self._with_humanized_mouse_destination(transformed_action)
                    if action.type == ActionType.WAIT:
                        wait_seconds = float(action.params.get("seconds", action.duration or action.delay))
                        if not self._wait_seconds(scaled_delay(wait_seconds, self.speed), mouse_controller):
                            return False, index
                    elif action.type == ActionType.MOUSE_MOVE:
                        if not self._play_mouse_move(transformed_action, mouse_controller):
                            return False, index
                    elif action.type == ActionType.IMAGE_CLICK:
                        self._clear_humanized_mouse_destination()
                        image_found = self._play_image_click(transformed_action, executor, mouse_controller)
                        if image_found is None:
                            return False, index
                        self._last_image_found = image_found
                    elif action.type == ActionType.IF_CONDITION:
                        jump_index = self._conditional_jump_index(action, len(actions))
                        if jump_index is not None:
                            self.status.emit(f"If Image Result jumped to action {jump_index + 1}")
                            next_index = jump_index
                    else:
                        executor.execute(transformed_action)
                except Exception as exc:
                    action_name = action.type.value.replace("_", " ").title()
                    raise RuntimeError(f"{context_label}, action {index + 1} ({action_name}): {exc}") from exc
                progress_signal.emit(index, action)
                if next_index != index + 1:
                    break
            index = next_index
        return True, index

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
        source_points = _mouse_move_points(action)
        if not source_points:
            self._clear_humanized_mouse_destination()
            return True
        start_override = None
        if (
            self._humanized_mouse_source == (source_points[0][0], source_points[0][1])
            and self._humanized_mouse_destination is not None
        ):
            start_override = self._humanized_mouse_destination
        self._clear_humanized_mouse_destination()
        points = _playback_mouse_points(
            action,
            self.current_environment.virtual_desktop,
            start_override=start_override,
        )
        if not points:
            return True
        start_time = time.perf_counter()
        for x, y, relative_time in points:
            if not self._wait_until(start_time + (relative_time / self.speed), mouse_controller):
                return False
            position_mouse(mouse_controller, int(x), int(y))
        if bool(action.params.get("humanize_playback", False)):
            self._humanized_mouse_source = (source_points[-1][0], source_points[-1][1])
            self._humanized_mouse_destination = (points[-1][0], points[-1][1])
        return True

    def _with_humanized_mouse_destination(self, action: MacroAction) -> MacroAction:
        params = action.params
        target = (params.get("x"), params.get("y"))
        if (
            self._humanized_mouse_source is not None
            and self._humanized_mouse_destination is not None
            and target == self._humanized_mouse_source
        ):
            varied_params = dict(params)
            varied_params["x"], varied_params["y"] = self._humanized_mouse_destination
            return action.with_changes(params=varied_params)
        self._clear_humanized_mouse_destination()
        return action

    def _clear_humanized_mouse_destination(self) -> None:
        self._humanized_mouse_source = None
        self._humanized_mouse_destination = None

    def _play_image_click(self, action: MacroAction, executor: ActionExecutor, mouse_controller: object) -> bool | None:
        def stop_check() -> bool:
            if self._paused:
                return self._wait_while_paused_or_stopped(mouse_controller)
            return self.safety.should_stop(getattr(mouse_controller, "position", None))

        match = find_image_match_for_action(action, stop_check=stop_check)
        if match is None:
            if stop_check():
                return None
            if str(action.params.get("on_not_found", "error")) == "skip":
                return False
            raise ValueError(f"Image not found on screen: {action.params.get('image_path', '')}")
        click_action = str(action.params.get("click_action", "left_click"))
        natural_movement = bool(action.params.get("natural_movement", False))
        if natural_movement or click_action == "custom_movement":
            result = self._play_image_custom_movement(action, match, executor, mouse_controller)
            if result is not True:
                return result
            if natural_movement and click_action not in {"move_only", "custom_movement"}:
                executor.apply_image_click_at_current_position(action)
            return True
        executor.click_image_match(action, match)
        return True

    def _play_image_custom_movement(
        self,
        action: MacroAction,
        match: object,
        executor: ActionExecutor,
        mouse_controller: object,
    ) -> bool | None:
        current_position = getattr(mouse_controller, "position", None)
        start_position = None
        if current_position is not None:
            start_position = (int(current_position[0]), int(current_position[1]))
        points = image_movement_points_for_match(
            action,
            match,
            start_position=start_position,
            bounds=self.current_environment.virtual_desktop,
        )
        if not points:
            return True
        interpolated_points = _interpolated_mouse_points(points)
        if not interpolated_points:
            return True
        first_x, first_y, _ = interpolated_points[0]
        position_mouse(mouse_controller, int(first_x), int(first_y))
        apply_movement_button = str(action.params.get("click_action", "left_click")) == "custom_movement"
        if apply_movement_button:
            executor.apply_image_movement_button(action, "start")
        start_time = time.perf_counter()
        for x, y, relative_time in interpolated_points[1:]:
            if not self._wait_until(start_time + (relative_time / self.speed), mouse_controller):
                return None
            position_mouse(mouse_controller, int(x), int(y))
        if apply_movement_button:
            executor.apply_image_movement_button(action, "end")
        return True

    def _conditional_jump_index(self, action: MacroAction, action_count: int | None = None) -> int | None:
        if self._last_image_found is None:
            return None
        target_key = "image_found_action" if self._last_image_found else "image_not_found_action"
        try:
            action_number = int(action.params.get(target_key, 0) or 0)
        except (TypeError, ValueError):
            action_number = 0
        if action_number <= 0:
            return None
        target_index = action_number - 1
        if not 0 <= target_index < (len(self.actions) if action_count is None else action_count):
            raise ValueError(f"If Image Result target is outside the macro: action {action_number}")
        return target_index

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
        if action.type not in {ActionType.MOUSE_MOVE, ActionType.MOUSE_BUTTON, ActionType.SCROLL, ActionType.IMAGE_CLICK}:
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
        elif action.type in {ActionType.MOUSE_BUTTON, ActionType.SCROLL}:
            if "x" in params and "y" in params:
                params["x"], params["y"] = transform_point(
                    int(params["x"]),
                    int(params["y"]),
                    self.recorded_environment,
                    self.current_environment,
                    mode=self.coordinate_mode,
                )
        elif bool(params.get("natural_movement", False)) and str(params.get("movement_start_mode", "cursor")) == "screen":
            start_center = params.get("movement_start_center")
            if isinstance(start_center, (list, tuple)) and len(start_center) >= 2:
                params["movement_start_center"] = list(
                    transform_point(
                        int(start_center[0]),
                        int(start_center[1]),
                        self.recorded_environment,
                        self.current_environment,
                        mode=self.coordinate_mode,
                    )
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
    return interpolated_path_points(points, hz=MOUSE_PLAYBACK_HZ)


def _playback_mouse_points(
    action: MacroAction,
    bounds: object,
    *,
    rng: object | None = None,
    start_override: tuple[int, int] | None = None,
) -> list[tuple[int, int, float]]:
    points = _mouse_move_points(action)
    if not bool(action.params.get("humanize_playback", False)):
        return _interpolated_mouse_points(points)
    if points and start_override is not None:
        points[0] = (int(start_override[0]), int(start_override[1]), points[0][2])
    return [
        (*clamp_point(x, y, bounds), relative_time)
        for x, y, relative_time in humanized_path_points(points, hz=MOUSE_PLAYBACK_HZ, rng=rng)
    ]
