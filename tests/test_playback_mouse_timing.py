from __future__ import annotations

from macro_recorder_plus.playback.playback_worker import _interpolated_mouse_points, _mouse_move_points
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
