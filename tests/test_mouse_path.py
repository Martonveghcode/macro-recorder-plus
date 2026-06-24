from __future__ import annotations

from macro_recorder_plus.utilities.mouse_path import simplify_path


def test_simplifies_straight_mouse_path():
    points = [(0, 0, 0.0), (1, 1, 0.1), (2, 2, 0.2), (10, 10, 1.0)]

    simplified = simplify_path(points, tolerance=1.0)

    assert simplified == [points[0], points[-1]]


def test_preserves_corner_in_mouse_path():
    points = [(0, 0, 0.0), (10, 0, 0.5), (10, 10, 1.0)]

    simplified = simplify_path(points, tolerance=1.0)

    assert (10, 0, 0.5) in simplified
