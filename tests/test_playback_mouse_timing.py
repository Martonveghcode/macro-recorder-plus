from __future__ import annotations

import math
import random
from types import SimpleNamespace

from macro_recorder_plus.models.environment import RecordedEnvironment, Rect
from macro_recorder_plus.playback.playback_worker import (
    PlaybackWorker,
    _interpolated_mouse_points,
    _mouse_move_points,
    _playback_mouse_points,
)
from macro_recorder_plus.playback import playback_worker
from macro_recorder_plus.models.actions import ActionType, MacroAction


def test_mouse_move_points_falls_back_to_start_end_duration():
    action = MacroAction(
        type=ActionType.MOUSE_MOVE,
        timestamp=2.0,
        duration=1.5,
        params={"start": [10, 20], "end": [40, 50], "path": []},
    )

    assert _mouse_move_points(action) == [(10, 20, 2.0), (40, 50, 3.5)]


def test_interpolates_mouse_path_at_sixty_hz():
    points = [(0, 0, 10.0), (60, 0, 11.0)]

    interpolated = _interpolated_mouse_points(points)

    assert len(interpolated) == 61
    assert interpolated[0] == (0, 0, 0.0)
    assert interpolated[-1] == (60, 0, 1.0)
    assert interpolated[30] == (30, 0, 0.5)


def test_only_tagged_mouse_moves_are_humanized():
    bounds = Rect(-1000, -1000, 1000, 1000)
    legacy = MacroAction(
        type=ActionType.MOUSE_MOVE,
        timestamp=0.0,
        duration=1.0,
        params={"start": [0, 0], "end": [100, 0], "path": []},
    )
    newly_recorded = legacy.with_changes(params={**legacy.params, "humanize_playback": True})

    legacy_points = _playback_mouse_points(legacy, bounds, rng=random.Random(7))
    varied_points = _playback_mouse_points(newly_recorded, bounds, rng=random.Random(7))

    assert legacy_points[-1] == (100, 0, 1.0)
    assert math.hypot(varied_points[-1][0] - 100, varied_points[-1][1]) <= 5
    assert varied_points != legacy_points


def test_following_click_uses_the_humanized_mouse_destination():
    worker = PlaybackWorker([])
    worker._humanized_mouse_source = (100, 200)
    worker._humanized_mouse_destination = (103, 196)
    click = MacroAction(
        type=ActionType.MOUSE_BUTTON,
        params={"x": 100, "y": 200, "button": "left", "phase": "press"},
    )

    varied_click = worker._with_humanized_mouse_destination(click)

    assert (varied_click.params["x"], varied_click.params["y"]) == (103, 196)


def test_chained_image_movement_smoothly_reaches_the_next_start_without_teleport(monkeypatch):
    class RecordingMouse:
        def __init__(self):
            self._position = (100, 100)
            self.positions = []

        @property
        def position(self):
            return self._position

        @position.setter
        def position(self, value):
            self._position = (int(value[0]), int(value[1]))
            self.positions.append(self._position)

    mouse = RecordingMouse()
    environment = RecordedEnvironment(virtual_desktop=Rect(0, 0, 1920, 1080))
    worker = PlaybackWorker([], current_environment_snapshot=environment)
    action = MacroAction(
        type=ActionType.IMAGE_CLICK,
        params={"natural_movement": True, "click_action": "left_click"},
    )

    monkeypatch.setattr(
        playback_worker,
        "image_movement_points_for_match",
        lambda *args, **kwargs: [(500, 300, 0.0), (800, 500, 0.5)],
    )
    monkeypatch.setattr(playback_worker, "_interpolated_mouse_points", lambda points: points)
    monkeypatch.setattr(
        playback_worker,
        "image_chain_transition_points",
        lambda start, end: [(100, 100, 0.0), (300, 200, 0.15), (500, 300, 0.3)],
    )
    monkeypatch.setattr(worker, "_wait_until", lambda target, mouse_controller: True)

    result = worker._play_image_custom_movement(
        action,
        SimpleNamespace(center=(800, 500)),
        SimpleNamespace(apply_image_movement_button=lambda action, stage: None),
        mouse,
        chain_from_previous_image=True,
    )

    assert result is True
    assert mouse.positions == [(300, 200), (500, 300), (800, 500)]
