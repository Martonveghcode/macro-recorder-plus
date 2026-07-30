from __future__ import annotations

import math
import random

from macro_recorder_plus.models.environment import Rect
from macro_recorder_plus.playback.playback_worker import (
    PlaybackWorker,
    _interpolated_mouse_points,
    _mouse_move_points,
    _playback_mouse_points,
)
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
