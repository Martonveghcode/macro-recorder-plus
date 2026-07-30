from __future__ import annotations

import math
import random

from macro_recorder_plus.utilities.mouse_path import humanized_path_points, simplify_path


def test_simplifies_straight_mouse_path():
    points = [(0, 0, 0.0), (1, 1, 0.1), (2, 2, 0.2), (10, 10, 1.0)]

    simplified = simplify_path(points, tolerance=1.0)

    assert simplified == [points[0], points[-1]]


def test_preserves_corner_in_mouse_path():
    points = [(0, 0, 0.0), (10, 0, 0.5), (10, 10, 1.0)]

    simplified = simplify_path(points, tolerance=1.0)

    assert (10, 0, 0.5) in simplified


def test_humanized_path_stays_near_destination_and_varies_shape_and_timing():
    points = [(0, 0, 10.0), (100, 0, 11.0)]

    varied = humanized_path_points(points, rng=random.Random(7))

    assert varied[0] == (0, 0, 0.0)
    assert math.hypot(varied[-1][0] - 100, varied[-1][1]) <= 5
    assert 0.1 <= abs(varied[-1][2] - 1.0) <= 0.2
    assert any(y != 0 for _, y, _ in varied[1:-1])


def test_humanized_short_path_uses_slower_timing_variance():
    points = [(0, 0, 0.0), (10, 0, 0.05)]

    varied = humanized_path_points(points, rng=random.Random(11))

    assert 0.15 <= varied[-1][2] <= 0.25
