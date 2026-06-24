from __future__ import annotations

from macro_recorder_plus.models.environment import RecordedEnvironment, Rect
from macro_recorder_plus.platform.windows_monitors import transform_point


def test_scaled_coordinate_transform_and_clamp():
    recorded = RecordedEnvironment(virtual_desktop=Rect(0, 0, 100, 100))
    current = RecordedEnvironment(virtual_desktop=Rect(-200, 0, 200, 200))

    assert transform_point(50, 50, recorded, current, mode="scaled") == (0, 100)
    assert transform_point(999, 999, recorded, current, mode="exact") == (199, 199)
