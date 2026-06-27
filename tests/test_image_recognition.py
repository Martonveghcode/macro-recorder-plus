from __future__ import annotations

from PIL import Image, ImageDraw

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.platform import windows_input
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


def test_legacy_timeout_zero_image_click_does_not_wait_forever(monkeypatch):
    captured = {}

    def fake_find_image_on_screen(image_path, **kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(windows_input, "find_image_on_screen", fake_find_image_on_screen)
    action = MacroAction(type=ActionType.IMAGE_CLICK, params={"image_path": "button.png", "timeout": 0.0})

    assert windows_input.find_image_match_for_action(action) is None
    assert captured["wait_until_found"] is False
