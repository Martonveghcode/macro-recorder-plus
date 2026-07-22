from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

from PIL import Image, ImageDraw

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.platform import windows_input
from macro_recorder_plus.platform.windows_input import ActionExecutor
from macro_recorder_plus.utilities.image_recognition import locate_image_in_image


def test_locates_template_center_with_confidence():
    screenshot = Image.new("RGB", (80, 60), "white")
    draw = ImageDraw.Draw(screenshot)
    draw.rectangle((30, 20, 44, 34), fill="red")
    template = screenshot.crop((30, 20, 45, 35))

    match = locate_image_in_image(screenshot, template, confidence=0.99, grayscale=False)

    assert match is not None
    assert match.x == 30
    assert match.y == 20
    assert match.center == (37, 27)
    assert match.confidence >= 0.99


def test_returns_none_when_template_is_missing():
    screenshot = Image.new("RGB", (80, 60), "white")
    template = Image.new("RGB", (10, 10), "blue")

    assert locate_image_in_image(screenshot, template, confidence=0.95, grayscale=False) is None


def test_locates_template_after_brightness_change():
    screenshot = Image.new("RGB", (120, 80), "white")
    button = Image.new("RGB", (26, 18), (60, 120, 220))
    draw = ImageDraw.Draw(button)
    draw.rectangle((2, 2, 23, 15), outline=(10, 40, 100), width=2)
    draw.line((6, 9, 20, 9), fill=(255, 255, 255), width=2)
    brighter = button.point(lambda value: min(255, int(value * 1.18 + 8)))
    screenshot.paste(brighter, (58, 31))

    match = locate_image_in_image(screenshot, button, confidence=0.75, grayscale=True)

    assert match is not None
    assert abs(match.x - 58) <= 1
    assert abs(match.y - 31) <= 1


def test_locates_template_after_small_scale_change():
    screenshot = Image.new("RGB", (140, 90), "white")
    button = Image.new("RGB", (30, 20), (40, 180, 90))
    draw = ImageDraw.Draw(button)
    draw.rectangle((3, 3, 26, 16), outline=(0, 80, 35), width=2)
    draw.ellipse((12, 6, 18, 12), fill=(255, 255, 255))
    scaled = button.resize((32, 21))
    screenshot.paste(scaled, (71, 42))

    match = locate_image_in_image(screenshot, button, confidence=0.75, grayscale=True, scale_tolerance=0.08)

    assert match is not None
    assert abs(match.x - 71) <= 1
    assert abs(match.y - 42) <= 1


def test_image_click_passes_wait_frequency_to_matcher(monkeypatch):
    captured = {}

    def fake_find_image_on_screen(image_path, **kwargs):
        captured["image_path"] = image_path
        captured.update(kwargs)
        return None

    monkeypatch.setattr(windows_input, "find_image_on_screen", fake_find_image_on_screen)
    action = MacroAction(
        type=ActionType.IMAGE_CLICK,
        params={
            "image_path": "button.png",
            "wait_until_found": True,
            "timeout": 0.0,
            "checks_per_second": 12.0,
            "on_not_found": "skip",
        },
    )

    assert windows_input.find_image_match_for_action(action) is None
    assert captured["image_path"] == "button.png"
    assert captured["wait_until_found"] is True
    assert captured["timeout"] == 0.0
    assert captured["checks_per_second"] == 12.0
    assert captured["poll_interval"] == 0.25
    assert captured["verification_attempts"] == 2
    assert captured["stable_match_pixels"] == 8
    assert captured["scale_tolerance"] == 0.05


def test_legacy_timeout_zero_image_click_does_not_wait_forever(monkeypatch):
    captured = {}

    def fake_find_image_on_screen(image_path, **kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(windows_input, "find_image_on_screen", fake_find_image_on_screen)
    action = MacroAction(type=ActionType.IMAGE_CLICK, params={"image_path": "button.png", "timeout": 0.0})

    assert windows_input.find_image_match_for_action(action) is None
    assert captured["wait_until_found"] is False


def test_custom_image_movement_uses_offsets_and_button_hold(monkeypatch):
    class FakeMouseController:
        def __init__(self) -> None:
            self.position = (0, 0)
            self.calls: list[tuple[str, str, tuple[int, int]]] = []

        def press(self, button: str) -> None:
            self.calls.append(("press", button, self.position))

        def release(self, button: str) -> None:
            self.calls.append(("release", button, self.position))

    pynput_module = ModuleType("pynput")
    pynput_module.mouse = SimpleNamespace(Button=SimpleNamespace(left="left", right="right", middle="middle"))
    monkeypatch.setitem(sys.modules, "pynput", pynput_module)

    mouse = FakeMouseController()
    executor = ActionExecutor(None, mouse)
    action = MacroAction(
        type=ActionType.IMAGE_CLICK,
        params={
            "click_action": "custom_movement",
            "movement_start_offset": [5, -2],
            "movement_end_offset": [10, 5],
            "movement_duration": 0.0,
            "movement_button": "left",
            "movement_button_action": "hold_during_move",
        },
    )

    executor.click_image_match(action, SimpleNamespace(center=(100, 200)))

    assert mouse.position == (110, 205)
    assert mouse.calls == [("press", "left", (105, 198)), ("release", "left", (110, 205))]
