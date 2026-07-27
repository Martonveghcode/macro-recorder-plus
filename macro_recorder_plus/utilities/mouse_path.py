from __future__ import annotations

import math
from collections.abc import Sequence

Point = tuple[int, int, float]


def simplify_path(points: Sequence[Point], tolerance: float) -> list[Point]:
    if len(points) <= 2 or tolerance <= 0:
        return list(points)

    first = points[0]
    last = points[-1]
    max_distance = -1.0
    split_index = 0
    for index in range(1, len(points) - 1):
        distance = _perpendicular_distance(points[index], first, last)
        if distance > max_distance:
            max_distance = distance
            split_index = index

    if max_distance > tolerance:
        left = simplify_path(points[: split_index + 1], tolerance)
        right = simplify_path(points[split_index:], tolerance)
        return left[:-1] + right
    return [first, last]


def _perpendicular_distance(point: Point, start: Point, end: Point) -> float:
    x, y, _ = point
    x1, y1, _ = start
    x2, y2, _ = end
    if x1 == x2 and y1 == y2:
        return math.hypot(x - x1, y - y1)
    numerator = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1)
    denominator = math.hypot(y2 - y1, x2 - x1)
    return numerator / denominator


def path_to_json(points: Sequence[Point]) -> list[list[float]]:
    return [[int(x), int(y), round(float(t), 6)] for x, y, t in points]


def interpolated_path_points(points: Sequence[Point], *, hz: int = 60) -> list[Point]:
    if len(points) <= 1:
        return list(points)

    first_time = points[0][2]
    output = [(points[0][0], points[0][1], 0.0)]
    for previous, current in zip(points, points[1:], strict=False):
        x1, y1, t1 = previous
        x2, y2, t2 = current
        segment_duration = max(0.0, t2 - t1)
        steps = max(1, math.ceil(segment_duration * hz))
        for step in range(1, steps + 1):
            alpha = step / steps
            x = round(x1 + (x2 - x1) * alpha)
            y = round(y1 + (y2 - y1) * alpha)
            relative_time = max(0.0, (t1 - first_time) + (segment_duration * alpha))
            output.append((x, y, relative_time))
    return output
