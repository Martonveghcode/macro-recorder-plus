from __future__ import annotations

from types import SimpleNamespace

from macro_recorder_plus.models.actions import ActionType, MacroAction
from macro_recorder_plus.models.environment import MonitorInfo, Rect
from macro_recorder_plus.platform.windows_input import keyboard_key_to_name
from macro_recorder_plus.recorder import input_recorder
from macro_recorder_plus.recorder.input_recorder import InputRecorder


def test_input_recorder_annotates_mouse_action_monitor(qtbot):
    recorder = InputRecorder()
    recorder._monitors = [
        MonitorInfo(
            identifier="DISPLAY1",
            bounds=Rect(0, 0, 100, 100),
            work_area=Rect(0, 0, 100, 100),
            primary=True,
        )
    ]
    action = MacroAction(type=ActionType.MOUSE_BUTTON, params={"x": 10, "y": 20, "button": "left", "phase": "click"})

    recorder._annotate_monitor(action)

    assert action.params["monitor"] == "DISPLAY1"


def test_keyboard_key_name_recovers_letter_from_ctrl_character():
    key = SimpleNamespace(char="\x03", vk=0x43)

    assert keyboard_key_to_name(key) == "c"


def test_input_recorder_collapses_ctrl_shortcuts_into_clean_hotkey_actions(qtbot, monkeypatch):
    recorder = InputRecorder()
    recorder._running = True
    recorder._normalizer.reset(0.0)
    recorder.options.ignored_keys = set()
    actions: list[MacroAction] = []
    recorder.actionRecorded.connect(actions.append)
    times = iter(value / 10 for value in range(1, 20))
    monkeypatch.setattr(input_recorder, "monotonic_seconds", lambda: next(times))

    ctrl = "Key.ctrl_l"
    recorder._on_key_press(ctrl)
    for char, virtual_key in [("\x01", 0x41), ("\x03", 0x43), ("\x16", 0x56), ("\x18", 0x58)]:
        key = SimpleNamespace(char=char, vk=virtual_key)
        recorder._on_key_press(key)
        recorder._on_key_release(key)
    recorder._on_key_release(ctrl)

    assert [action.type for action in actions] == [ActionType.HOTKEY] * 4
    assert [action.params["keys"] for action in actions] == [
        ["ctrl", "a"],
        ["ctrl", "c"],
        ["ctrl", "v"],
        ["ctrl", "x"],
    ]


def test_shifted_text_remains_raw_keyboard_input(qtbot, monkeypatch):
    recorder = InputRecorder()
    recorder._running = True
    recorder._normalizer.reset(0.0)
    recorder.options.ignored_keys = set()
    actions: list[MacroAction] = []
    recorder.actionRecorded.connect(actions.append)
    times = iter(value / 10 for value in range(1, 10))
    monkeypatch.setattr(input_recorder, "monotonic_seconds", lambda: next(times))

    shift = "Key.shift_l"
    letter = SimpleNamespace(char="A", vk=0x41)
    recorder._on_key_press(shift)
    recorder._on_key_press(letter)
    recorder._on_key_release(letter)
    recorder._on_key_release(shift)

    assert [(action.params["key"], action.params["phase"]) for action in actions] == [
        ("shift", "press"),
        ("a", "press"),
        ("a", "release"),
        ("shift", "release"),
    ]


def test_standalone_modifier_tap_is_not_lost(qtbot, monkeypatch):
    recorder = InputRecorder()
    recorder._running = True
    recorder._normalizer.reset(0.0)
    recorder.options.ignored_keys = set()
    actions: list[MacroAction] = []
    recorder.actionRecorded.connect(actions.append)
    times = iter([0.1, 0.2])
    monkeypatch.setattr(input_recorder, "monotonic_seconds", lambda: next(times))

    recorder._on_key_press("Key.ctrl_l")
    recorder._on_key_release("Key.ctrl_l")

    assert [(action.params["key"], action.params["phase"]) for action in actions] == [
        ("ctrl", "press"),
        ("ctrl", "release"),
    ]
