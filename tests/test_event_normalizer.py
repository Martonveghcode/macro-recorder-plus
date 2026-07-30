from __future__ import annotations

from macro_recorder_plus.models.actions import ActionType
from macro_recorder_plus.recorder.event_normalizer import EventNormalizer


def test_event_normalizer_emits_hotkey_action():
    normalizer = EventNormalizer()
    normalizer.reset(10.0)

    actions = normalizer.add_hotkey(["ctrl", "v"], 10.25)

    assert len(actions) == 1
    assert actions[0].type == ActionType.HOTKEY
    assert actions[0].params["keys"] == ["ctrl", "v"]


def test_newly_recorded_mouse_move_enables_humanized_playback():
    normalizer = EventNormalizer()
    normalizer.reset(10.0)
    normalizer.add_mouse_move(10, 20, 10.0)
    normalizer.add_mouse_move(50, 60, 10.5)

    actions = normalizer.flush_mouse_move()

    assert len(actions) == 1
    assert actions[0].type == ActionType.MOUSE_MOVE
    assert actions[0].params["humanize_playback"] is True


def test_click_coordinate_becomes_the_recorded_mouse_path_destination():
    normalizer = EventNormalizer()
    normalizer.reset(10.0)
    normalizer.add_mouse_move(10, 20, 10.0)
    normalizer.add_mouse_move(40, 50, 10.25)

    actions = normalizer.add_mouse_button(44, 53, "left", "press", 10.3)

    assert [action.type for action in actions] == [ActionType.MOUSE_MOVE, ActionType.MOUSE_BUTTON]
    assert actions[0].params["end"] == [44, 53]
    assert actions[0].params["path"][-1] == [44, 53, 0.3]


def test_drag_path_starts_at_mouse_press_coordinate():
    normalizer = EventNormalizer()
    normalizer.reset(10.0)
    press = normalizer.add_mouse_button(10, 20, "left", "press", 10.0)
    normalizer.add_mouse_move(50, 60, 10.5)
    release = normalizer.add_mouse_button(80, 90, "left", "release", 11.0)

    assert [action.type for action in press] == [ActionType.MOUSE_BUTTON]
    assert [action.type for action in release] == [ActionType.MOUSE_MOVE, ActionType.MOUSE_BUTTON]
    assert release[0].params["start"] == [10, 20]
    assert release[0].params["end"] == [80, 90]
