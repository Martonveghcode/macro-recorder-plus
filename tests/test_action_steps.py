from __future__ import annotations

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.utilities.action_steps import LogicalActionStep, logical_action_steps, step_at_or_after, step_before


def _key(key: str, phase: str) -> MacroAction:
    return MacroAction(type=ActionType.KEY_PRESS, params={"key": key, "phase": phase})


def _mouse(button: str, phase: str) -> MacroAction:
    return MacroAction(type=ActionType.MOUSE_BUTTON, params={"button": button, "phase": phase, "x": 10, "y": 20})


def test_modern_shortcuts_each_form_one_logical_step():
    actions = [
        MacroAction(type=ActionType.HOTKEY, params={"keys": ["ctrl", key]})
        for key in ["a", "c", "x", "v"]
    ]

    assert logical_action_steps(actions) == [
        LogicalActionStep(0, 1),
        LogicalActionStep(1, 2),
        LogicalActionStep(2, 3),
        LogicalActionStep(3, 4),
    ]


def test_legacy_ctrl_chord_is_kept_atomic():
    actions = [
        _key("ctrl", "press"),
        _key("v", "press"),
        _key("v", "release"),
        _key("ctrl", "release"),
        MacroAction(type=ActionType.MOUSE_MOVE, params={"start": [0, 0], "end": [10, 10]}),
    ]

    assert logical_action_steps(actions) == [LogicalActionStep(0, 4), LogicalActionStep(4, 5)]


def test_mouse_press_move_release_is_one_drag_step():
    actions = [
        _mouse("left", "press"),
        MacroAction(type=ActionType.MOUSE_MOVE, params={"start": [10, 20], "end": [30, 40]}),
        _mouse("left", "release"),
    ]

    assert logical_action_steps(actions) == [LogicalActionStep(0, 3)]


def test_step_navigation_uses_logical_boundaries():
    steps = [LogicalActionStep(0, 4), LogicalActionStep(4, 5), LogicalActionStep(5, 7)]

    assert step_at_or_after(steps, 2) == steps[0]
    assert step_at_or_after(steps, 4) == steps[1]
    assert step_before(steps, 5) == steps[1]
    assert step_before(steps, 0) is None
