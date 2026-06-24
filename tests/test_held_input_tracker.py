from __future__ import annotations

from macro_recorder_plus.platform.windows_input import HeldInputTracker


class DummyController:
    def __init__(self):
        self.calls = []

    def press(self, value):
        self.calls.append(("press", value))

    def release(self, value):
        self.calls.append(("release", value))


def test_releases_held_keys_and_buttons():
    keyboard = DummyController()
    mouse = DummyController()
    tracker = HeldInputTracker(keyboard, mouse)

    tracker.press_key("ctrl")
    tracker.press_button("left")
    tracker.release_all()

    assert tracker.held_keys == []
    assert tracker.held_buttons == []
    assert ("release", "ctrl") in keyboard.calls
    assert ("release", "left") in mouse.calls
