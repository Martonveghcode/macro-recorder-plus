from __future__ import annotations

import ctypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


DEFAULT_VERIFICATION_ATTEMPTS = 2
DEFAULT_STABLE_MATCH_PIXELS = 8
DEFAULT_SCALE_TOLERANCE = 0.05


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
    verification_attempts: int = DEFAULT_VERIFICATION_ATTEMPTS,
    stable_match_pixels: int = DEFAULT_STABLE_MATCH_PIXELS,
    scale_tolerance: float = DEFAULT_SCALE_TOLERANCE,
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
    required_stable_matches = max(1, int(verification_attempts or 1))
    stable_pixels = max(0, int(stable_match_pixels or 0))
    best_streak_match: ImageMatch | None = None
    stable_count = 0
    checked_once = False

    while True:
        if stop_check is not None and stop_check():
            return None
        screenshot, offset_x, offset_y = _grab_screen(ImageGrab, region)
        local_match = locate_image_in_image(
            screenshot,
            template,
            confidence=confidence,
            grayscale=grayscale,
            scale_tolerance=scale_tolerance,
        )
        checked_once = True
        if local_match is not None:
            match = ImageMatch(
                x=local_match.x + offset_x,
                y=local_match.y + offset_y,
                width=local_match.width,
                height=local_match.height,
                confidence=local_match.confidence,
            )
            if _matches_are_stable(best_streak_match, match, max_center_distance=stable_pixels):
                stable_count += 1
                if match.confidence >= best_streak_match.confidence:  # type: ignore[union-attr]
                    best_streak_match = match
            else:
                best_streak_match = match
                stable_count = 1
            if stable_count >= required_stable_matches:
                return best_streak_match
        else:
            best_streak_match = None
            stable_count = 0
            if not wait_until_found and checked_once:
                required_misses = max(1, int(verification_attempts or 1))
                required_misses -= 1
                if required_misses <= 0:
                    return None
                for _ in range(required_misses):
                    if not _sleep_with_stop_check(min(poll_seconds, 0.05), stop_check):
                        return None
                    screenshot, offset_x, offset_y = _grab_screen(ImageGrab, region)
                    local_match = locate_image_in_image(
                        screenshot,
                        template,
                        confidence=confidence,
                        grayscale=grayscale,
                        scale_tolerance=scale_tolerance,
                    )
                    if local_match is not None:
                        best_streak_match = ImageMatch(
                            x=local_match.x + offset_x,
                            y=local_match.y + offset_y,
                            width=local_match.width,
                            height=local_match.height,
                            confidence=local_match.confidence,
                        )
                        stable_count = 1
                        break
                if stable_count == 0:
                    return None

        if not wait_until_found and local_match is not None and stable_count < required_stable_matches:
            # Verification found something once, but it was not stable enough. Try the remaining
            # quick verification captures before deciding the one-shot check failed.
            remaining = required_stable_matches - stable_count
            for _ in range(max(0, remaining)):
                if not _sleep_with_stop_check(min(poll_seconds, 0.05), stop_check):
                    return None
                screenshot, offset_x, offset_y = _grab_screen(ImageGrab, region)
                local_match = locate_image_in_image(
                    screenshot,
                    template,
                    confidence=confidence,
                    grayscale=grayscale,
                    scale_tolerance=scale_tolerance,
                )
                if local_match is None:
                    best_streak_match = None
                    stable_count = 0
                    break
                match = ImageMatch(
                    x=local_match.x + offset_x,
                    y=local_match.y + offset_y,
                    width=local_match.width,
                    height=local_match.height,
                    confidence=local_match.confidence,
                )
                if _matches_are_stable(best_streak_match, match, max_center_distance=stable_pixels):
                    stable_count += 1
                    if match.confidence >= best_streak_match.confidence:  # type: ignore[union-attr]
                        best_streak_match = match
                else:
                    best_streak_match = match
                    stable_count = 1
                if stable_count >= required_stable_matches:
                    return best_streak_match
            return None

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
    scale_tolerance: float = DEFAULT_SCALE_TOLERANCE,
) -> ImageMatch | None:
    import numpy as np

    confidence = min(1.0, max(0.0, float(confidence)))
    screen_rgb = _image_to_rgb_array(screenshot, np=np)
    template_rgb = _image_to_rgb_array(template, np=np)

    screen_height, screen_width = screen_rgb.shape[:2]
    template_height, template_width = template_rgb.shape[:2]
    if template_width <= 0 or template_height <= 0:
        return None
    if template_width > screen_width or template_height > screen_height:
        return None

    cv2_match = _locate_with_cv2(screen_rgb, template_rgb, confidence, grayscale=grayscale, scale_tolerance=scale_tolerance)
    if cv2_match is not None:
        x, y, width, height, score = cv2_match
        return ImageMatch(x=x, y=y, width=width, height=height, confidence=score)

    # Fallback path for machines without OpenCV. It is slower and less tolerant than the
    # OpenCV path, but keeps the app functional with only Pillow + NumPy installed.
    screen_array = _image_to_array(screenshot, grayscale=grayscale, np=np)
    template_array = _image_to_array(template, grayscale=grayscale, np=np)
    screen_height, screen_width = screen_array.shape[:2]
    template_height, template_width = template_array.shape[:2]
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
    return np.asarray(converted, dtype=np.float32)


def _image_to_rgb_array(image: Any, *, np: Any) -> Any:
    return np.asarray(image.convert("RGB"), dtype=np.uint8)


def _locate_with_cv2(
    screen_rgb: Any,
    template_rgb: Any,
    confidence: float,
    *,
    grayscale: bool,
    scale_tolerance: float,
) -> tuple[int, int, int, int, float] | None:
    try:
        import cv2
        import numpy as np
    except Exception:
        return None

    screen_gray = cv2.cvtColor(screen_rgb, cv2.COLOR_RGB2GRAY)
    template_gray = cv2.cvtColor(template_rgb, cv2.COLOR_RGB2GRAY)
    best: tuple[int, int, int, int, float] | None = None

    for scaled_template_rgb, scaled_template_gray in _scaled_templates(template_rgb, template_gray, scale_tolerance, cv2=cv2, np=np):
        template_height, template_width = scaled_template_gray.shape[:2]
        if template_width <= 0 or template_height <= 0:
            continue
        if template_width > screen_gray.shape[1] or template_height > screen_gray.shape[0]:
            continue

        attempts: list[tuple[Any, Any, int]] = []
        gray_std = float(np.std(scaled_template_gray))
        attempts.append((screen_gray, scaled_template_gray, cv2.TM_SQDIFF_NORMED))
        if gray_std >= 1.0:
            attempts.append((screen_gray, scaled_template_gray, cv2.TM_CCOEFF_NORMED))
            attempts.append((cv2.equalizeHist(screen_gray), cv2.equalizeHist(scaled_template_gray), cv2.TM_CCOEFF_NORMED))
            screen_edges = cv2.Canny(screen_gray, 50, 150)
            template_edges = cv2.Canny(scaled_template_gray, 50, 150)
            if int(np.count_nonzero(template_edges)) >= max(8, template_width * template_height // 80):
                attempts.append((screen_edges, template_edges, cv2.TM_CCOEFF_NORMED))

        if not grayscale:
            attempts.append((screen_rgb, scaled_template_rgb, cv2.TM_SQDIFF_NORMED))
            if float(np.std(scaled_template_rgb)) >= 1.0:
                attempts.append((screen_rgb, scaled_template_rgb, cv2.TM_CCOEFF_NORMED))

        for screen_variant, template_variant, method in attempts:
            try:
                score, location = _best_cv2_location(screen_variant, template_variant, method, cv2=cv2)
            except Exception:
                continue
            if best is None or score > best[4]:
                x, y = location
                best = (int(x), int(y), int(template_width), int(template_height), float(score))

    if best is None or best[4] < confidence:
        return None
    return best


def _scaled_templates(template_rgb: Any, template_gray: Any, scale_tolerance: float, *, cv2: Any, np: Any) -> list[tuple[Any, Any]]:
    tolerance = max(0.0, min(0.25, float(scale_tolerance or 0.0)))
    scales = [1.0]
    if tolerance > 0:
        scales.extend([1.0 - tolerance * 0.4, 1.0 + tolerance * 0.4, 1.0 - tolerance, 1.0 + tolerance])
    output: list[tuple[Any, Any]] = []
    seen: set[tuple[int, int]] = set()
    height, width = template_gray.shape[:2]
    for scale in scales:
        scaled_width = max(1, int(round(width * scale)))
        scaled_height = max(1, int(round(height * scale)))
        key = (scaled_width, scaled_height)
        if key in seen:
            continue
        seen.add(key)
        if scale == 1.0:
            output.append((template_rgb, template_gray))
            continue
        interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
        output.append(
            (
                cv2.resize(template_rgb, key, interpolation=interpolation),
                cv2.resize(template_gray, key, interpolation=interpolation),
            )
        )
    return output


def _best_cv2_location(screen: Any, template: Any, method: int, *, cv2: Any) -> tuple[float, tuple[int, int]]:
    result = cv2.matchTemplate(screen, template, method)
    min_value, max_value, min_location, max_location = cv2.minMaxLoc(result)
    if method == cv2.TM_SQDIFF_NORMED:
        return 1.0 - float(min_value), min_location
    return float(max_value), max_location


def _matches_are_stable(previous: ImageMatch | None, current: ImageMatch, *, max_center_distance: int) -> bool:
    if previous is None:
        return False
    prev_x, prev_y = previous.center
    curr_x, curr_y = current.center
    return abs(prev_x - curr_x) <= max_center_distance and abs(prev_y - curr_y) <= max_center_distance


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
