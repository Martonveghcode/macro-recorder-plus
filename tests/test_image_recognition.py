from __future__ import annotations

from PIL import Image, ImageDraw

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
