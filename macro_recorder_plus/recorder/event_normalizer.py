from __future__ import annotations

from dataclasses import dataclass

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.utilities.mouse_path import Point, path_to_json, simplify_path


@dataclass(slots=True)
class NormalizerOptions:
    mouse_sample_hz: int = 60
    simplification_tolerance: float = 2.0


class EventNormalizer:
    def __init__(self, options: NormalizerOptions | None = None) -> None:
        self.options = options or NormalizerOptions()
        self._start_time = 0.0
        self._last_action_time = 0.0
        self._move_points: list[Point] = []
        self._last_move_sample_time = -1.0

    def reset(self, start_time: float) -> None:
        self._start_time = start_time
        self._last_action_time = 0.0
        self._move_points = []
        self._last_move_sample_time = -1.0

    def add_mouse_move(self, x: int, y: int, now: float) -> list[MacroAction]:
        timestamp = now - self._start_time
        sample_interval = 1.0 / max(1, self.options.mouse_sample_hz)
        if self._last_move_sample_time >= 0 and timestamp - self._last_move_sample_time < sample_interval:
            return []
        self._last_move_sample_time = timestamp
        self._move_points.append((int(x), int(y), timestamp))
        return []

    def flush_mouse_move(self) -> list[MacroAction]:
        if len(self._move_points) < 2:
            self._move_points.clear()
            return []
        points = simplify_path(self._move_points, self.options.simplification_tolerance)
        start = points[0]
        end = points[-1]
        duration = max(0.0, end[2] - start[2])
        action = self._make_action(
            ActionType.MOUSE_MOVE,
            timestamp=start[2],
            duration=duration,
            params={
                "start": [start[0], start[1]],
                "end": [end[0], end[1]],
                "path": path_to_json(points),
                "coordinate_mode": "exact",
            },
        )
        self._move_points.clear()
        return [action]

    def add_keyboard(self, key: str, phase: str, now: float) -> list[MacroAction]:
        return self.flush_mouse_move() + [
            self._make_action(
                ActionType.KEY_PRESS,
                timestamp=now - self._start_time,
                params={"key": key, "phase": phase},
            )
        ]

    def add_hotkey(self, keys: list[str], now: float) -> list[MacroAction]:
        return self.flush_mouse_move() + [
            self._make_action(
                ActionType.HOTKEY,
                timestamp=now - self._start_time,
                params={"keys": keys},
            )
        ]

    def add_mouse_button(self, x: int, y: int, button: str, phase: str, now: float) -> list[MacroAction]:
        return self.flush_mouse_move() + [
            self._make_action(
                ActionType.MOUSE_BUTTON,
                timestamp=now - self._start_time,
                params={"x": int(x), "y": int(y), "button": button, "phase": phase},
            )
        ]

    def add_scroll(self, x: int, y: int, dx: int, dy: int, now: float) -> list[MacroAction]:
        return self.flush_mouse_move() + [
            self._make_action(
                ActionType.SCROLL,
                timestamp=now - self._start_time,
                params={"x": int(x), "y": int(y), "dx": int(dx), "dy": int(dy)},
            )
        ]

    def _make_action(
        self,
        action_type: ActionType,
        *,
        timestamp: float,
        params: dict,
        duration: float = 0.0,
    ) -> MacroAction:
        delay = max(0.0, timestamp - self._last_action_time)
        self._last_action_time = max(self._last_action_time, timestamp + duration)
        return MacroAction(type=action_type, timestamp=timestamp, delay=delay, duration=duration, params=params)
