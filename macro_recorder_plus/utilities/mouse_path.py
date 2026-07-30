from __future__ import annotations

import math
import random
from collections.abc import Sequence
from typing import Any

Point = tuple[int, int, float]

HUMANIZED_ENDPOINT_RADIUS = 5
HUMANIZED_PATH_VARIANCE = 2.0
HUMANIZED_TIMING_VARIANCE_MIN = 0.1
HUMANIZED_TIMING_VARIANCE_MAX = 0.2
IMAGE_CHAIN_TRANSITION_DURATION_MIN = 0.3
IMAGE_CHAIN_TRANSITION_DURATION_MAX = 0.8
IMAGE_CHAIN_TRANSITION_PATH_VARIANCE = 4.0


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


def humanized_path_points(
    points: Sequence[Point],
    *,
    hz: int = 60,
    endpoint_radius: int = HUMANIZED_ENDPOINT_RADIUS,
    path_variance: float = HUMANIZED_PATH_VARIANCE,
    timing_variance_min: float = HUMANIZED_TIMING_VARIANCE_MIN,
    timing_variance_max: float = HUMANIZED_TIMING_VARIANCE_MAX,
    rng: Any | None = None,
) -> list[Point]:
    """Return a smooth, slightly varied rendering of a recorded mouse path."""
    base_points = interpolated_path_points(points, hz=hz)
    if len(base_points) <= 1:
        return base_points

    random_source = rng or random
    endpoint_dx, endpoint_dy = random_circle_offset(max(0, int(endpoint_radius)), random_source)

    minimum_timing_variance = max(0.0, float(timing_variance_min))
    maximum_timing_variance = max(minimum_timing_variance, float(timing_variance_max))
    timing_variance = random_source.uniform(minimum_timing_variance, maximum_timing_variance)
    base_duration = max(0.0, float(base_points[-1][2]))
    if base_duration > timing_variance and random_source.random() < 0.5:
        varied_duration = base_duration - timing_variance
    else:
        varied_duration = base_duration + timing_variance

    maximum_wiggle = max(0.0, float(path_variance))
    primary_amplitude = random_source.uniform(maximum_wiggle * 0.35, maximum_wiggle * 0.75)
    secondary_amplitude = random_source.uniform(maximum_wiggle * 0.1, maximum_wiggle * 0.25)
    primary_phase = random_source.uniform(0.0, math.tau)
    secondary_phase = random_source.uniform(0.0, math.tau)

    output: list[Point] = []
    last_index = len(base_points) - 1
    for index, (x, y, relative_time) in enumerate(base_points):
        if base_duration > 0:
            progress = min(1.0, max(0.0, float(relative_time) / base_duration))
        else:
            progress = index / last_index

        previous = base_points[max(0, index - 1)]
        following = base_points[min(last_index, index + 1)]
        tangent_x = float(following[0] - previous[0])
        tangent_y = float(following[1] - previous[1])
        tangent_length = math.hypot(tangent_x, tangent_y)
        if tangent_length:
            normal_x = -tangent_y / tangent_length
            normal_y = tangent_x / tangent_length
        else:
            normal_x = 0.0
            normal_y = 0.0

        taper = math.sin(math.pi * progress)
        wiggle = taper * (
            primary_amplitude * math.sin((math.tau * progress) + primary_phase)
            + secondary_amplitude * math.sin((2.0 * math.tau * progress) + secondary_phase)
        )
        endpoint_ease = progress * progress * (3.0 - (2.0 * progress))
        varied_x = round(float(x) + (endpoint_dx * endpoint_ease) + (normal_x * wiggle))
        varied_y = round(float(y) + (endpoint_dy * endpoint_ease) + (normal_y * wiggle))
        varied_time = varied_duration * progress
        output.append((varied_x, varied_y, varied_time))

    output[0] = (int(base_points[0][0]), int(base_points[0][1]), 0.0)
    output[-1] = (
        int(base_points[-1][0]) + endpoint_dx,
        int(base_points[-1][1]) + endpoint_dy,
        varied_duration,
    )
    return output


def image_chain_transition_points(
    start: tuple[int, int],
    end: tuple[int, int],
    *,
    rng: Any | None = None,
) -> list[Point]:
    """Build the short natural bridge between consecutive image actions."""
    random_source = rng or random
    duration = random_source.uniform(
        IMAGE_CHAIN_TRANSITION_DURATION_MIN,
        IMAGE_CHAIN_TRANSITION_DURATION_MAX,
    )
    return humanized_path_points(
        [
            (int(start[0]), int(start[1]), 0.0),
            (int(end[0]), int(end[1]), duration),
        ],
        hz=60,
        endpoint_radius=0,
        path_variance=IMAGE_CHAIN_TRANSITION_PATH_VARIANCE,
        timing_variance_min=0.0,
        timing_variance_max=0.0,
        rng=random_source,
    )


def random_circle_offset(radius: int, rng: Any | None = None) -> tuple[int, int]:
    """Pick an integer offset uniformly from the pixels inside a radius."""
    random_source = rng or random
    if radius <= 0:
        return 0, 0
    while True:
        dx = random_source.randint(-radius, radius)
        dy = random_source.randint(-radius, radius)
        if (dx * dx) + (dy * dy) <= radius * radius:
            return dx, dy
