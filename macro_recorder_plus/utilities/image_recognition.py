from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class ImageMatch:
    x: int
    y: int
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


def find_image_on_screen(
    image_path: str | Path,
    *,
    confidence: float = 0.85,
    timeout: float = 5.0,
    poll_interval: float = 0.25,
    checks_per_second: float | None = None,
    wait_until_found: bool = True,
    grayscale: bool = True,
    region: tuple[int, int, int, int] | None = None,
    stop_check: Callable[[], bool] | None = None,
) -> ImageMatch | None:
    from PIL import Image, ImageGrab

    template_path = Path(image_path).expanduser()
    if not template_path.exists():
        raise FileNotFoundError(f"Image not found: {template_path}")

    template = Image.open(template_path)
    timeout_seconds = max(0.0, float(timeout))
    poll_seconds = poll_interval_from_frequency(poll_interval, checks_per_second)
    deadline = None if wait_until_found and timeout_seconds <= 0 else time.perf_counter() + timeout_seconds
    while True:
        if stop_check is not None and stop_check():
            return None
        screenshot, offset_x, offset_y = _grab_screen(ImageGrab, region)
        match = locate_image_in_image(screenshot, template, confidence=confidence, grayscale=grayscale)
        if match is not None:
            return ImageMatch(
                x=match.x + offset_x,
                y=match.y + offset_y,
                width=match.width,
                height=match.height,
                confidence=match.confidence,
            )
        if not wait_until_found:
            return None
        if deadline is not None and time.perf_counter() >= deadline:
            return None
        sleep_seconds = poll_seconds if deadline is None else min(poll_seconds, max(0.0, deadline - time.perf_counter()))
        if not _sleep_with_stop_check(sleep_seconds, stop_check):
            return None


def poll_interval_from_frequency(poll_interval: float = 0.25, checks_per_second: float | None = None) -> float:
    if checks_per_second is not None:
        return max(0.01, 1.0 / max(0.1, float(checks_per_second)))
    return max(0.05, float(poll_interval))


def locate_image_in_image(
    screenshot: Any,
    template: Any,
    *,
    confidence: float = 0.85,
    grayscale: bool = True,
    max_full_checks: int = 2000,
) -> ImageMatch | None:
    import numpy as np

    confidence = min(1.0, max(0.0, float(confidence)))
    screen_array = _image_to_array(screenshot, grayscale=grayscale, np=np)
    template_array = _image_to_array(template, grayscale=grayscale, np=np)

    screen_height, screen_width = screen_array.shape[:2]
    template_height, template_width = template_array.shape[:2]
    if template_width <= 0 or template_height <= 0:
        return None
    if template_width > screen_width or template_height > screen_height:
        return None

    cv2_match = _locate_with_cv2(screen_array, template_array, confidence)
    if cv2_match is not None:
        x, y, score = cv2_match
        return ImageMatch(x=x, y=y, width=template_width, height=template_height, confidence=score)

    candidate_height = screen_height - template_height + 1
    candidate_width = screen_width - template_width + 1
    mask = np.ones((candidate_height, candidate_width), dtype=bool)
    sample_points = _sample_points(template_width, template_height)
    pixel_threshold = max(8.0, (1.0 - confidence) * 255.0 * 3.0)

    for sample_x, sample_y in sample_points:
        screen_slice = screen_array[sample_y : sample_y + candidate_height, sample_x : sample_x + candidate_width]
        template_pixel = template_array[sample_y, sample_x]
        diff = np.abs(screen_slice - template_pixel)
        if diff.ndim == 3:
            diff = diff.mean(axis=2)
        mask &= diff <= pixel_threshold
        if not mask.any():
            return None

    candidate_rows, candidate_cols = np.nonzero(mask)
    if len(candidate_rows) == 0:
        return None

    if len(candidate_rows) > max_full_checks:
        candidate_rows, candidate_cols = _best_sampled_candidates(
            screen_array,
            template_array,
            candidate_rows,
            candidate_cols,
            sample_points,
            np=np,
            limit=max_full_checks,
        )

    best: tuple[int, int, float] | None = None
    for y, x in zip(candidate_rows, candidate_cols, strict=False):
        window = screen_array[y : y + template_height, x : x + template_width]
        diff = np.abs(window - template_array)
        score = 1.0 - float(diff.mean()) / 255.0
        if best is None or score > best[2]:
            best = (int(x), int(y), score)

    if best is None or best[2] < confidence:
        return None
    return ImageMatch(x=best[0], y=best[1], width=template_width, height=template_height, confidence=best[2])


def _grab_screen(image_grab_module: Any, region: tuple[int, int, int, int] | None) -> tuple[Any, int, int]:
    if region is not None:
        x, y, width, height = region
        screenshot = image_grab_module.grab(bbox=(x, y, x + width, y + height))
        return screenshot, int(x), int(y)

    try:
        screenshot = image_grab_module.grab(all_screens=True)
        return screenshot, *_virtual_screen_origin()
    except TypeError:
        return image_grab_module.grab(), 0, 0


def _sleep_with_stop_check(seconds: float, stop_check: Callable[[], bool] | None) -> bool:
    target = time.perf_counter() + max(0.0, seconds)
    while True:
        if stop_check is not None and stop_check():
            return False
        remaining = target - time.perf_counter()
        if remaining <= 0:
            return True
        time.sleep(min(remaining, 0.05))


def _virtual_screen_origin() -> tuple[int, int]:
    if not hasattr(ctypes, "windll"):
        return (0, 0)
    try:
        user32 = ctypes.windll.user32
        return (int(user32.GetSystemMetrics(76)), int(user32.GetSystemMetrics(77)))
    except Exception:
        return (0, 0)


def _image_to_array(image: Any, *, grayscale: bool, np: Any) -> Any:
    converted = image.convert("L" if grayscale else "RGB")
    array = np.asarray(converted, dtype=np.float32)
    if grayscale:
        return array
    return array


def _locate_with_cv2(screen_array: Any, template_array: Any, confidence: float) -> tuple[int, int, float] | None:
    try:
        import cv2
        import numpy as np
    except Exception:
        return None

    if float(np.std(template_array)) < 0.001:
        return None

    method = cv2.TM_CCOEFF_NORMED
    result = cv2.matchTemplate(screen_array, template_array, method)
    _, max_value, _, max_location = cv2.minMaxLoc(result)
    score = float(max_value)
    if score < confidence:
        return None
    x, y = max_location
    return int(x), int(y), score


def _sample_points(width: int, height: int) -> list[tuple[int, int]]:
    x_values = sorted({0, width // 4, width // 2, (width * 3) // 4, width - 1})
    y_values = sorted({0, height // 4, height // 2, (height * 3) // 4, height - 1})
    points = [(x, y) for y in y_values for x in x_values]
    step_x = max(1, width // 6)
    step_y = max(1, height // 6)
    for y in range(0, height, step_y):
        for x in range(0, width, step_x):
            points.append((min(width - 1, x), min(height - 1, y)))
    return list(dict.fromkeys(points))


def _best_sampled_candidates(
    screen_array: Any,
    template_array: Any,
    candidate_rows: Any,
    candidate_cols: Any,
    sample_points: list[tuple[int, int]],
    *,
    np: Any,
    limit: int,
) -> tuple[Any, Any]:
    scores = np.zeros(len(candidate_rows), dtype=np.float32)
    for sample_x, sample_y in sample_points:
        screen_values = screen_array[candidate_rows + sample_y, candidate_cols + sample_x]
        template_pixel = template_array[sample_y, sample_x]
        diff = np.abs(screen_values - template_pixel)
        if diff.ndim == 2:
            diff = diff.mean(axis=1)
        scores += diff
    scores /= max(1, len(sample_points))
    best_indexes = np.argsort(scores)[:limit]
    return candidate_rows[best_indexes], candidate_cols[best_indexes]
